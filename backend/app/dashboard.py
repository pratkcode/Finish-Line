"""One-call summary of a planning session for the dashboard."""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.courses import CourseSummary
from app.db import get_connection
from app.degree_progress import calculate_degree_progress
from app.eligibility import analyze_eligibility
from app.graduation_plan import build_student_plan, load_context
from app.requirements import Program

router = APIRouter(prefix="/api/sessions", tags=["dashboard"])


class CreditTotals(BaseModel):
    earned: int  # completed credit that counts toward the degree
    from_courses: int
    in_progress: int  # being taken now; not counted yet
    unverified: int  # recorded but not counted until verified
    required: int | None
    remaining: int | None


class RequirementTotals(BaseModel):
    complete: int
    remaining: int
    not_tracked: int
    percent: int  # complete / (complete + remaining), rounded


class GraduationSummary(BaseModel):
    projected: str | None  # from the student's saved plan
    note: str
    semesters: int  # semesters with planned courses
    planned_courses: int
    warnings: int  # problems in the saved plan


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
    plan_start_term: str
    max_credits_per_term: int
    completed_courses: int
    in_progress_courses: int
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
    plan = build_student_plan(context)
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
        "plan_start_term": plan["plan_start_term"],
        "max_credits_per_term": session["max_credits_per_term"],
        "completed_courses": len(context["record"].completed),
        "in_progress_courses": len(context["record"].in_progress),
        "credits": {"earned": credits["applicable"], "from_courses": credits["from_courses"],
                    "in_progress": credits["in_progress"],
                    "unverified": credits["unverified"], "required": credits["required"],
                    "remaining": credits["remaining"]},
        "requirements": {"complete": complete, "remaining": remaining,
                         "not_tracked": len(progress["untracked_requirements"]),
                         "percent": round(100 * complete / tracked) if tracked else 100},
        "graduation": {"projected": plan["projected_graduation"],
                       "note": plan["graduation_note"],
                       "semesters": len(plan["terms"]),
                       "planned_courses": sum(len(t["courses"]) for t in plan["terms"]),
                       "warnings": len(plan["warnings"])},
        "next_term": {"term": first["term"], "credits": first["credits"],
                      "courses": [c["code"] for c in first["courses"]]}
        if first else None,
        "eligibility": {"available": len(eligibility["available"]),
                        "blocked": len(eligibility["blocked"])},
        "top_prerequisite": {k: missing[0][k] for k in ("code", "name", "credits_min",
                                                        "credits_max")} if missing else None,
    }
