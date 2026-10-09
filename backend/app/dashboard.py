"""One-call summary of a planning session for the dashboard."""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.courses import CourseSummary
from app.db import get_connection
from app.degree_progress import calculate_degree_progress
from app.eligibility import analyze_eligibility
from app.graduation_plan import load_context, load_overrides, make_plan
from app.requirements import Program

router = APIRouter(prefix="/api/sessions", tags=["dashboard"])


class CreditTotals(BaseModel):
    earned: int  # from courses plus reported credits
    from_courses: int
    unverified: int  # reported but not matched to a course
    required: int | None
    remaining: int | None


class RequirementTotals(BaseModel):
    complete: int
    remaining: int
    not_tracked: int
    percent: int  # complete / (complete + remaining), rounded


class GraduationSummary(BaseModel):
    projected: str | None
    semesters: int
    warnings: int  # problems caused by the student's own changes
    has_changes: bool  # the student has edited the generated plan


class NextTerm(BaseModel):
    term: str
    credits: int
    courses: list[str]  # course codes, or slot names


class EligibilityTotals(BaseModel):
    available: int
    blocked: int


class DashboardSummary(BaseModel):
    session_id: UUID
    program: Program
    current_term: str | None
    max_credits_per_term: int
    completed_courses: int
    credits: CreditTotals
    requirements: RequirementTotals
    graduation: GraduationSummary
    next_term: NextTerm | None
    eligibility: EligibilityTotals
    top_prerequisite: CourseSummary | None  # the missing course that unlocks the most


@router.get("/{session_id}/summary", response_model=DashboardSummary)
def get_summary(session_id: UUID):
    with get_connection() as conn:
        progress = calculate_degree_progress(conn, session_id)
        eligibility = analyze_eligibility(conn, session_id, progress)
        context = load_context(conn, session_id)
        overrides = load_overrides(conn, session_id)
    plan = make_plan(context, overrides)
    session = context["session"]

    complete = len(progress["completed_requirements"])
    remaining = len(progress["remaining_requirements"])
    tracked = complete + remaining
    credits = progress["credits"]
    first = plan["terms"][0] if plan["terms"] else None
    missing = eligibility["missing_prerequisites"]

    return {
        "session_id": session_id,
        "program": progress["program"],
        "current_term": session["current_term"],
        "max_credits_per_term": session["max_credits_per_term"],
        "completed_courses": len(session["courses"]),
        "credits": {"earned": credits["counted"], "from_courses": credits["from_courses"],
                    "unverified": credits["unverified"], "required": credits["required"],
                    "remaining": credits["remaining"]},
        "requirements": {"complete": complete, "remaining": remaining,
                         "not_tracked": len(progress["untracked_requirements"]),
                         "percent": round(100 * complete / tracked) if tracked else 100},
        "graduation": {"projected": plan["projected_graduation"],
                       "semesters": len(plan["terms"]),
                       "warnings": len(plan["warnings"]),
                       "has_changes": bool(overrides["pinned"] or overrides["removed"])},
        "next_term": {"term": first["term"], "credits": first["credits"],
                      "courses": [c["code"] or c["name"] for c in first["courses"]]}
        if first else None,
        "eligibility": {"available": len(eligibility["available"]),
                        "blocked": len(eligibility["blocked"])},
        "top_prerequisite": {k: missing[0][k] for k in ("code", "name", "credits_min",
                                                        "credits_max")} if missing else None,
    }
