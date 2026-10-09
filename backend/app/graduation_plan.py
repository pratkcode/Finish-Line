"""API route for the generated graduation plan (see app/planner.py)."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.courses import normalize_code
from app.db import get_connection
from app.planner import build_plan, first_planned_term, terms_after
from app.restrictions import load_rules
from app.prerequisites import load_graph
from app.requirements import find_program, load_requirements
from app.sessions import load_session

router = APIRouter(prefix="/api/sessions", tags=["graduation plan"])


class RequirementRef(BaseModel):
    key: str | None
    name: str
    category: str | None


class PlannedCourse(BaseModel):
    code: str | None  # None for "choose a course" slots and general electives
    name: str
    credits: int
    kind: Literal["course", "placeholder", "elective"]
    required: bool
    retake: bool
    satisfies: list[RequirementRef]  # degree requirements this fills
    prerequisites: list[str]  # planned courses this depends on
    notes: list[str]  # restrictions and conditions to check
    pinned: bool  # placed by the student
    warnings: list[str]  # rules this placement breaks


class PlannedTerm(BaseModel):
    term: str
    credits: int
    warnings: list[str]  # e.g. over the credit limit
    courses: list[PlannedCourse]


class UnscheduledCourse(PlannedCourse):
    reason: str


class UnplannedRequirement(BaseModel):
    key: str
    name: str
    reason: str


class NotChecked(BaseModel):
    key: str
    name: str


class PlanWarning(BaseModel):
    term: str
    code: str | None
    message: str


class Placement(BaseModel):
    code: str
    term: str = Field(pattern=r"^(Spring|Fall) \d{4}$")


class Overrides(BaseModel):
    """The student's changes: courses placed in a semester, and courses removed."""
    pinned: list[Placement] = Field(default=[], max_length=100)
    removed: list[str] = Field(default=[], max_length=100)


class PlanCredits(BaseModel):
    remaining: int  # still to earn: required minus completed
    completed: int  # from completed courses plus reported credits
    planned: int  # new credits from the plan (retakes don't add credits)
    total: int
    required: int | None


class GraduationPlan(BaseModel):
    disclaimer: str
    start_term: str
    max_credits_per_term: int
    projected_graduation: str | None
    graduation_note: str
    warnings: list[PlanWarning]
    pinned: list[Placement]
    removed: list[str]
    credits: PlanCredits
    terms: list[PlannedTerm]
    unscheduled: list[UnscheduledCourse]
    unplanned_requirements: list[UnplannedRequirement]
    not_checked: list[NotChecked]  # e.g. GPA, residency
    assumptions: list[str]


class MovedCourse(BaseModel):
    code: str
    name: str
    from_term: str | None  # None = newly in the plan
    to_term: str | None  # None = no longer in the plan


class PlanChanges(BaseModel):
    graduation_before: str | None
    graduation_after: str | None
    moved: list[MovedCourse]


class PlanPreview(GraduationPlan):
    changes: PlanChanges  # compared with the saved plan


TermQuery = Annotated[str | None, Query(pattern=r"^(Spring|Summer|Fall|Winter) \d{4}$")]
CreditsQuery = Annotated[int | None, Query(ge=1, le=30)]


@router.get("/{session_id}/plan", response_model=GraduationPlan)
def get_graduation_plan(session_id: UUID, start_term: TermQuery = None,
                        max_credits: CreditsQuery = None):
    """Generate a recommended semester plan for the session, including the
    student's saved changes. Defaults come from the session's current semester
    and maximum credits per semester."""
    with get_connection() as conn:
        context = load_context(conn, session_id)
        overrides = load_overrides(conn, session_id)
    return make_plan(context, overrides, start_term, max_credits)


@router.post("/{session_id}/plan/preview", response_model=PlanPreview)
def preview_graduation_plan(session_id: UUID, body: Overrides):
    """What if: the plan with these changes instead of the saved ones (nothing is saved)."""
    with get_connection() as conn:
        context = load_context(conn, session_id)
        saved = load_overrides(conn, session_id)
    overrides = check_overrides(context, body)
    before = make_plan(context, saved)
    after = make_plan(context, overrides)
    return {**after, "changes": compare(before, after)}


@router.put("/{session_id}/plan/overrides", response_model=GraduationPlan)
def save_plan_overrides(session_id: UUID, body: Overrides):
    """Save the student's changes (replaces any saved ones)."""
    with get_connection() as conn:
        context = load_context(conn, session_id)
        overrides = check_overrides(context, body)
        conn.execute("DELETE FROM plan_overrides WHERE session_id = %s", (session_id,))
        for code, term in overrides["pinned"].items():
            conn.execute(
                """
                INSERT INTO plan_overrides (session_id, course_id, term)
                SELECT %s, id, %s FROM courses WHERE code = %s AND university_id = %s
                """,
                (session_id, term, code, context["program"]["university_id"]),
            )
        for code in overrides["removed"]:
            conn.execute(
                """
                INSERT INTO plan_overrides (session_id, course_id, removed)
                SELECT %s, id, TRUE FROM courses WHERE code = %s AND university_id = %s
                """,
                (session_id, code, context["program"]["university_id"]),
            )
    return make_plan(context, overrides)


def load_context(conn, session_id: UUID) -> dict:
    session = load_session(conn, session_id)
    program = find_program(conn, session["program_slug"])
    tree, _ = load_requirements(conn, program)
    return {"session": session, "program": program, "tree": tree,
            "graph": load_graph(conn, program["university_id"]),
            "rules": load_rules(conn, program)}


def load_overrides(conn, session_id: UUID) -> dict:
    rows = conn.execute(
        """
        SELECT c.code, o.term, o.removed FROM plan_overrides o
        JOIN courses c ON c.id = o.course_id WHERE o.session_id = %s ORDER BY c.code
        """,
        (session_id,),
    ).fetchall()
    return {"pinned": {r["code"]: r["term"] for r in rows if not r["removed"]},
            "removed": {r["code"] for r in rows if r["removed"]}}


def start_of(context: dict, start_term: str | None = None) -> str:
    return first_planned_term(start_term or context["session"]["current_term"] or default_term())


def check_overrides(context: dict, body: Overrides) -> dict:
    graph, session = context["graph"], context["session"]
    start = start_of(context)
    completed = {c["code"] for c in session["courses"]}
    pinned, removed = {}, set()
    for placement in body.pinned:
        code = normalize_code(placement.code)
        if code not in graph.courses:
            raise HTTPException(status_code=404, detail=f"Course {code} not found")
        if code in completed:
            raise HTTPException(status_code=409, detail=f"{code} is already completed")
        if terms_after(start, placement.term) < 0:
            raise HTTPException(status_code=422,
                                detail=f"{placement.term} is before your plan starts ({start})")
        pinned[code] = placement.term
    for raw in body.removed:
        code = normalize_code(raw)
        if code not in graph.courses:
            raise HTTPException(status_code=404, detail=f"Course {code} not found")
        if code in pinned:
            raise HTTPException(status_code=422, detail=f"{code} can't be both placed and removed")
        removed.add(code)
    return {"pinned": pinned, "removed": removed}


def make_plan(context: dict, overrides: dict, start_term: str | None = None,
              max_credits: int | None = None) -> dict:
    session = context["session"]
    completed = {c["code"]: {"grade": c["grade"], "credits": c["credits"]}
                 for c in session["courses"]}
    return build_plan(context["tree"], context["graph"], context["rules"], completed,
                      session["credits"]["unmatched"], start_of(context, start_term),
                      max_credits or session["max_credits_per_term"],
                      overrides["pinned"], overrides["removed"])


def compare(before: dict, after: dict) -> dict:
    def placements(plan):
        return {c["code"]: (t["term"], c["name"]) for t in plan["terms"] for c in t["courses"]
                if c["code"]}
    old, new = placements(before), placements(after)
    moved = []
    for code in sorted(set(old) | set(new)):
        from_term = old.get(code, (None,))[0]
        to_term = new.get(code, (None,))[0]
        if from_term != to_term:
            name = (new.get(code) or old.get(code))[1]
            moved.append({"code": code, "name": name, "from_term": from_term, "to_term": to_term})
    return {"graduation_before": before["projected_graduation"],
            "graduation_after": after["projected_graduation"], "moved": moved}


def default_term() -> str:
    today = date.today()
    season = "Spring" if today.month <= 5 else "Fall"
    return f"{season} {today.year}"
