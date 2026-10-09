"""Prerequisite eligibility for a student's remaining courses (see app/prerequisites.py)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.courses import CourseSummary, normalize_code
from app.db import get_connection
from app.degree_progress import calculate_degree_progress
from app.prerequisites import Checker, load_graph
from app.requirements import find_program
from app.sessions import load_session

router = APIRouter(prefix="/api/sessions", tags=["eligibility"])


class PrerequisiteOption(CourseSummary):
    state: Literal["completed", "low_grade", "available", "blocked"]
    grade: str | None


class PrerequisiteGroupState(BaseModel):
    timing: Literal["before", "before_or_concurrent", "concurrent"]
    min_grade: str | None
    state: Literal["met", "concurrent", "missing"]
    options: list[PrerequisiteOption]  # any one satisfies the group


class RequirementRef(BaseModel):
    key: str
    name: str


class CourseEligibility(CourseSummary):
    status: Literal["completed", "available", "available_with_concurrent", "blocked"]
    groups: list[PrerequisiteGroupState]  # every group must be met
    complete_first: list[CourseSummary]  # in a workable order, deepest first
    take_with: list[CourseSummary]  # may be taken the same semester instead
    additional_conditions: str | None  # catalog conditions that aren't courses
    retake: bool = False  # taken before with too low a grade
    satisfies: list[RequirementRef] = []  # remaining requirements it could fill


class MissingPrerequisite(CourseSummary):
    status: Literal["completed", "available", "available_with_concurrent", "blocked"]
    unlocks: list[str]  # blocked remaining courses that need it first


class EligibilityAnalysis(BaseModel):
    session_id: UUID
    current_term: str | None
    available: list[CourseEligibility]
    blocked: list[CourseEligibility]
    missing_prerequisites: list[MissingPrerequisite]


@router.get("/{session_id}/eligibility", response_model=EligibilityAnalysis)
def get_eligibility(session_id: UUID):
    """Prerequisite status of every course that could fill a remaining requirement."""
    with get_connection() as conn:
        return analyze_eligibility(conn, session_id)


def analyze_eligibility(conn, session_id: UUID, progress: dict | None = None) -> dict:
    progress = progress or calculate_degree_progress(conn, session_id)
    session = load_session(conn, session_id)
    checker = student_checker(conn, session)

    satisfies: dict[str, list[dict]] = {}
    for unit in progress["remaining_requirements"]:
        for course in unit["candidate_courses"]:
            satisfies.setdefault(course["code"], []).append(
                {"key": unit["key"], "name": unit["name"]})

    available, blocked = [], []
    for code, requirements in satisfies.items():
        result = checker.check(code, retake=code in checker.completed)
        result["retake"] = code in checker.completed
        result["satisfies"] = requirements
        (blocked if result["status"] == "blocked" else available).append(result)

    unlocks: dict[str, list[str]] = {}
    for result in blocked:
        for course in result["complete_first"] + result["take_with"]:
            unlocks.setdefault(course["code"], []).append(result["code"])
    missing = [
        {**checker.ref(code),
         "status": checker.check(code, retake=code in checker.completed)["status"],
         "unlocks": codes}
        for code, codes in unlocks.items()
    ]
    missing.sort(key=lambda m: (-len(m["unlocks"]), m["code"]))
    return {"session_id": session_id, "current_term": session["current_term"],
            "available": available, "blocked": blocked, "missing_prerequisites": missing}


@router.get("/{session_id}/eligibility/{course_code}", response_model=CourseEligibility)
def get_course_eligibility(session_id: UUID, course_code: str):
    """Prerequisite status of one course for this student."""
    code = normalize_code(course_code)
    with get_connection() as conn:
        checker = student_checker(conn, load_session(conn, session_id))
    if code not in checker.graph.courses:
        raise HTTPException(status_code=404, detail=f"Course {code} not found")
    return checker.check(code)


def student_checker(conn, session: dict) -> Checker:
    program = find_program(conn, session["program_slug"])
    completed = {c["code"]: c["grade"] for c in session["courses"]}
    return Checker(load_graph(conn, program["university_id"]), completed)
