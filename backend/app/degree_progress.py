"""Degree progress for a student's planning session.

Loads the session's completed courses and the program's requirement tree from
the database, evaluates them with app.evaluator, and summarizes what's done,
what's left, and which courses could fill each gap.
"""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_connection
from app.evaluator import evaluate, meets_grade, walk
from app.restrictions import Rules, load_rules
from app.requirements import (
    AppliedCourse,
    Program,
    Requirement,
    Status,
    find_program,
    load_requirements,
)
from app.sessions import load_session

router = APIRouter(prefix="/api/sessions", tags=["degree progress"])

# Stand-in "course" for reported credits that aren't matched to a listed course
# (AP, transfer, ...). It only counts toward requirements where any course counts.
REPORTED = "REPORTED"


class CandidateCourse(BaseModel):
    code: str
    name: str
    credits_min: int
    credits_max: int
    # Set when the student took the course but the grade was too low to count.
    earned_grade: str | None = None


class RequirementSummary(BaseModel):
    key: str
    name: str
    path: list[str]  # names of the parent requirements, outermost first
    category: str
    rule: str
    status: Status
    min_grade: str | None
    courses_remaining: int | None
    credits_remaining: int | None
    applied_courses: list[AppliedCourse]
    # Courses that could still satisfy it. Empty when any course counts.
    candidate_courses: list[CandidateCourse]
    # "Complete one of" requirements list their options here.
    options: list[str]


class CreditSummary(BaseModel):
    from_courses: int  # credits of completed courses in the plan
    unverified: int  # reported credits not matched to a course (AP, transfer, ...)
    counted: int  # from_courses + unverified
    required: int | None  # degree total, from the requirement data
    remaining: int | None


class DegreeProgress(BaseModel):
    session_id: UUID
    program: Program
    credits: CreditSummary
    completed_requirements: list[RequirementSummary]
    remaining_requirements: list[RequirementSummary]
    untracked_requirements: list[RequirementSummary]
    requirements: list[Requirement]  # full tree with progress, for detail views


@router.get("/{session_id}/progress", response_model=DegreeProgress)
def get_degree_progress(session_id: UUID):
    with get_connection() as conn:
        return calculate_degree_progress(conn, session_id)


def calculate_degree_progress(conn, session_id: UUID) -> dict:
    session = load_session(conn, session_id)
    program = find_program(conn, session["program_slug"])
    tree, _ = load_requirements(conn, program)

    taken = {
        c["code"]: {"code": c["code"], "name": c["name"], "credits": c["credits"],
                    "grade": c["grade"]}
        for c in session["courses"]
    }
    add_reported_credits(tree, taken, session["credits"]["unmatched"])
    results = evaluate(tree, taken)
    for node in walk(tree):
        node["progress"] = results[node["key"]]

    summary = summarize(tree, taken, load_rules(conn, program))
    return {"session_id": session_id, "program": program, "requirements": tree, **summary}


def add_reported_credits(tree: list[dict], taken: dict[str, dict], credits: int) -> None:
    if credits <= 0:
        return
    taken[REPORTED] = {"code": REPORTED, "name": "Reported credits not matched to a course",
                       "credits": credits, "grade": None}
    for node in walk(tree):
        if node.get("any_course"):
            node["eligible"] = node["eligible"] + [REPORTED]


def summarize(tree: list[dict], taken: dict[str, dict], rules: Rules | None = None) -> dict:
    """Split an evaluated tree into completed / remaining / untracked units.

    A unit is a requirement the student acts on directly: a course rule, or a
    "complete one of" choice (whose options aren't listed separately).
    Optional requirements (e.g. cognate areas) are left out. With `rules`,
    courses the student can't take (other programs, credit overlaps, ...)
    aren't suggested.
    """
    # Courses a requirement names explicitly are suggested only there, not for
    # other requirements in the same allocation group (a core course retaken
    # counts toward the core, not as an elective).
    reserved = {}
    for node in walk(tree):
        if node["rule"] == "all_courses" and node["allocation_group"]:
            reserved.setdefault(node["allocation_group"], set()).update(node["eligible"])

    completed, remaining, untracked = [], [], []
    for unit, path in units(tree):
        status = unit["progress"]["status"]
        summary = summarize_unit(unit, path, taken, reserved, rules)
        if status == "complete":
            completed.append(summary)
        elif status == "not_tracked":
            untracked.append(summary)
        else:
            remaining.append(summary)

    from_courses = sum(c["credits"] for code, c in taken.items() if code != REPORTED)
    unverified = taken[REPORTED]["credits"] if REPORTED in taken else 0
    counted = from_courses + unverified
    total = [n["min_credits"] for n in walk(tree) if n.get("any_course") and n["min_credits"]]
    required = max(total) if total else None
    return {
        "credits": {
            "from_courses": from_courses,
            "unverified": unverified,
            "counted": counted,
            "required": required,
            "remaining": max(required - counted, 0) if required is not None else None,
        },
        "completed_requirements": completed,
        "remaining_requirements": remaining,
        "untracked_requirements": untracked,
    }


def units(nodes: list[dict], path: tuple[str, ...] = ()):
    for node in nodes:
        if node["optional"]:
            continue
        if node["rule"] == "all_children":
            yield from units(node["children"], path + (node["name"],))
        else:
            yield node, list(path)


def summarize_unit(node: dict, path: list[str], taken: dict[str, dict], reserved: dict,
                   rules: Rules | None = None) -> dict:
    progress = node["progress"]
    if node["rule"] == "any_child":
        # Collect the leaves of every option, then dedupe by course code.
        candidates = {}
        for child in walk(node["children"]):
            if not child["children"]:
                for course in candidate_courses(child, taken, reserved, rules):
                    candidates.setdefault(course["code"], course)
        candidate_list = list(candidates.values())
        applied = []
        for child in walk(node["children"]):
            if not child["children"]:
                for course in child["progress"]["applied_courses"]:
                    if course["code"] not in {c["code"] for c in applied}:
                        applied.append(course)
        options = [child["name"] for child in node["children"]]
    else:
        candidate_list = ([] if node.get("any_course")
                          else candidate_courses(node, taken, reserved, rules))
        applied = progress["applied_courses"]
        options = []

    if progress["status"] == "complete":
        candidate_list = []
    return {
        "key": node["key"],
        "name": node["name"],
        "path": path,
        "category": node["category"],
        "rule": node["rule"],
        "status": progress["status"],
        "min_grade": node["min_grade"],
        "courses_remaining": progress["courses_remaining"],
        "credits_remaining": progress["credits_remaining"],
        "applied_courses": applied,
        "candidate_courses": candidate_list,
        "options": options,
    }


def candidate_courses(node: dict, taken: dict[str, dict], reserved: dict,
                      rules: Rules | None = None) -> list[dict]:
    """Eligible courses the student hasn't already completed with a good enough
    grade. Courses taken with too low a grade stay in (they can be retaken)."""
    if node["rule"] in ("not_tracked", "course_list"):
        return []
    skip = set()
    if node["rule"] != "all_courses":
        skip = reserved.get(node["allocation_group"], set())
    have = set(taken)
    candidates = []
    for course in node["eligible_courses"]:
        if course["code"] in skip:
            continue
        # Required courses are always listed; elective-style choices skip
        # courses the student can't take.
        if rules and node["rule"] != "all_courses" and rules.blocked_reason(
                course["code"], have - {course["code"]}):
            continue
        earned = taken.get(course["code"])
        if earned and meets_grade(earned["grade"], node["min_grade"]):
            continue
        candidates.append({
            "code": course["code"], "name": course["name"],
            "credits_min": course["credits_min"], "credits_max": course["credits_max"],
            "earned_grade": earned["grade"] if earned else None,
        })
    return candidates
