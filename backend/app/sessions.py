"""A student's temporary planning session: profile and completed courses.

There are no accounts yet. Whoever holds a session id can use the session.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.courses import normalize_code
from app.db import get_connection
from app.evaluator import Grade
from app.requirements import find_program
from app.terms import PLAN_TERM_PATTERN, TERM_PATTERN, ordinal

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

Term = Annotated[str, Field(pattern=TERM_PATTERN, examples=["Fall 2026"])]
PlanTerm = Annotated[str, Field(pattern=PLAN_TERM_PATTERN, examples=["Spring 2027"])]
Status = Literal["completed", "in_progress"]
ReportedCredits = Annotated[int, Field(ge=0, le=300)]
MaxCredits = Annotated[int, Field(ge=1, le=30)]


class SessionCreate(BaseModel):
    program_slug: str
    reported_credits: ReportedCredits | None = None
    current_term: Term | None = None
    max_credits_per_term: MaxCredits = 15
    plan_start_term: PlanTerm | None = None
    target_graduation_term: Term | None = None
    academic_standing: str | None = Field(None, max_length=100)
    include_summer: bool = False
    max_summer_credits: MaxCredits | None = None


class SessionUpdate(BaseModel):
    # Only fields that are sent are changed; send null to clear an optional one.
    program_slug: str | None = None
    reported_credits: ReportedCredits | None = None
    current_term: Term | None = None
    max_credits_per_term: MaxCredits | None = None
    plan_start_term: PlanTerm | None = None
    target_graduation_term: Term | None = None
    academic_standing: str | None = Field(None, max_length=100)
    include_summer: bool | None = None
    max_summer_credits: MaxCredits | None = None


class CompletedCourseCreate(BaseModel):
    code: str
    grade: Grade | None = None
    credits: int | None = Field(None, description="Only needed for variable-credit courses")
    status: Status = "completed"  # in_progress: taking it now; not counted yet
    academic_term_id: int | None = None  # a UMD semester in the student's history


class CompletedCourseUpdate(BaseModel):
    grade: Grade | None = None
    credits: int | None = None
    status: Status | None = None
    academic_term_id: int | None = None


class CompletedCourse(BaseModel):
    code: str
    name: str
    credits: int
    credits_min: int
    credits_max: int
    grade: Grade | None
    status: Status
    academic_term_id: int | None


class Credits(BaseModel):
    # UMD courses marked completed (an F earns no credit).
    completed: int
    in_progress: int
    # What the student typed in, if anything.
    reported: int | None
    # Reported credits not backed by a course in the list (AP, transfer,
    # courses not added yet). 0 when nothing was reported.
    unmatched: int
    # True when the reported total is lower than the course list adds up to.
    reported_too_low: bool


class Session(BaseModel):
    id: UUID
    program_slug: str
    program_name: str
    university: str
    current_term: str | None
    max_credits_per_term: int
    plan_start_term: str | None  # None: the term after current_term
    target_graduation_term: str | None
    academic_standing: str | None
    include_summer: bool
    max_summer_credits: int | None
    courses: list[CompletedCourse]
    credits: Credits


@router.post("", response_model=Session, status_code=201)
def create_session(body: SessionCreate):
    with get_connection() as conn:
        program = find_program(conn, body.program_slug)
        row = conn.execute(
            """
            INSERT INTO planning_sessions (program_id, reported_credits, current_term,
                max_credits_per_term, plan_start_term, target_graduation_term,
                academic_standing, include_summer, max_summer_credits)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (program["id"], body.reported_credits, body.current_term, body.max_credits_per_term,
             body.plan_start_term, body.target_graduation_term, body.academic_standing,
             body.include_summer, body.max_summer_credits),
        ).fetchone()
        check_terms(load_session(conn, row["id"]))
        return load_session(conn, row["id"])


@router.get("/{session_id}", response_model=Session)
def get_session(session_id: UUID):
    with get_connection() as conn:
        return load_session(conn, session_id)


@router.patch("/{session_id}", response_model=Session)
def update_session(session_id: UUID, body: SessionUpdate):
    changes = body.model_dump(exclude_unset=True)
    with get_connection() as conn:
        session = load_session(conn, session_id)
        if "program_slug" in changes:
            if changes["program_slug"] is None:
                raise HTTPException(status_code=422, detail="program_slug cannot be null")
            program = find_program(conn, changes.pop("program_slug"))
            if program["university"] != session["university"] and session["courses"]:
                raise HTTPException(
                    status_code=409,
                    detail="Remove completed courses before switching to another university",
                )
            changes["program_id"] = program["id"]
        for required in ("max_credits_per_term", "include_summer"):
            if required in changes and changes[required] is None:
                raise HTTPException(status_code=422, detail=f"{required} cannot be null")
        if changes:
            columns = ", ".join(f"{column} = %({column})s" for column in changes)
            conn.execute(
                f"UPDATE planning_sessions SET {columns}, updated_at = now() WHERE id = %(id)s",
                {**changes, "id": session_id},
            )
        updated = load_session(conn, session_id)
        check_terms(updated)
        return updated


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: UUID):
    with get_connection() as conn:
        deleted = conn.execute(
            "DELETE FROM planning_sessions WHERE id = %s RETURNING id", (session_id,)
        ).fetchone()
    if deleted is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=204)


@router.get("/{session_id}/courses", response_model=list[CompletedCourse])
def list_completed_courses(session_id: UUID):
    with get_connection() as conn:
        return load_session(conn, session_id)["courses"]


@router.post("/{session_id}/courses", response_model=Session, status_code=201)
def add_completed_course(session_id: UUID, body: CompletedCourseCreate):
    with get_connection() as conn:
        session = load_session(conn, session_id)
        code = normalize_code(body.code)
        course = conn.execute(
            """
            SELECT c.id, c.credits_min, c.credits_max FROM courses c
            JOIN universities u ON u.id = c.university_id
            WHERE c.code = %s AND u.name = %s
            """,
            (code, session["university"]),
        ).fetchone()
        if course is None:
            raise HTTPException(status_code=404, detail=f"Course {code} not found")
        if any(c["code"] == code for c in session["courses"]):
            raise HTTPException(status_code=409, detail=f"{code} is already in your history")
        check_course_entry(conn, session_id, body.status, body.grade, body.academic_term_id)

        credits = check_credits(body.credits, course)
        conn.execute(
            """
            INSERT INTO session_courses (session_id, course_id, credits, grade, status,
                                         academic_term_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, course["id"], credits, body.grade, body.status, body.academic_term_id),
        )
        touch(conn, session_id)
        return load_session(conn, session_id)


@router.patch("/{session_id}/courses/{course_code}", response_model=Session)
def update_completed_course(session_id: UUID, course_code: str, body: CompletedCourseUpdate):
    changes = body.model_dump(exclude_unset=True)
    with get_connection() as conn:
        session = load_session(conn, session_id)
        code = normalize_code(course_code)
        course = next((c for c in session["courses"] if c["code"] == code), None)
        if course is None:
            raise HTTPException(status_code=404, detail=f"{code} is not a completed course")
        if "credits" in changes:
            changes["credits"] = check_credits(changes["credits"], course)
        if changes.get("status", 0) is None:
            raise HTTPException(status_code=422, detail="status cannot be null")
        merged = {**course, **changes}
        check_course_entry(conn, session_id, merged["status"], merged["grade"],
                           merged["academic_term_id"])
        if changes:
            columns = ", ".join(f"{column} = %({column})s" for column in changes)
            conn.execute(
                f"""
                UPDATE session_courses SET {columns}
                WHERE session_id = %(session_id)s
                  AND course_id IN (SELECT id FROM courses WHERE code = %(code)s)
                """,
                {**changes, "session_id": session_id, "code": code},
            )
            touch(conn, session_id)
        return load_session(conn, session_id)


@router.delete("/{session_id}/courses/{course_code}", response_model=Session)
def remove_completed_course(session_id: UUID, course_code: str):
    with get_connection() as conn:
        load_session(conn, session_id)
        code = normalize_code(course_code)
        deleted = conn.execute(
            """
            DELETE FROM session_courses
            WHERE session_id = %s AND course_id IN (SELECT id FROM courses WHERE code = %s)
            RETURNING course_id
            """,
            (session_id, code),
        ).fetchone()
        if deleted is None:
            raise HTTPException(status_code=404, detail=f"{code} is not a completed course")
        touch(conn, session_id)
        return load_session(conn, session_id)


def check_course_entry(conn, session_id: UUID, status: str, grade: str | None,
                       academic_term_id: int | None) -> None:
    if status == "in_progress" and grade is not None:
        raise HTTPException(status_code=422, detail="An in-progress course can't have a grade yet")
    if academic_term_id is not None:
        term = conn.execute(
            "SELECT at_umd FROM academic_terms WHERE id = %s AND session_id = %s",
            (academic_term_id, session_id),
        ).fetchone()
        if term is None:
            raise HTTPException(status_code=404, detail="That semester isn't in your history")
        if not term["at_umd"]:
            raise HTTPException(status_code=422, detail=(
                "UMD courses go in UMD semesters; record other schools' courses as transfer credit"))


def check_terms(session: dict) -> None:
    current, start = session["current_term"], session["plan_start_term"]
    if current and start and ordinal(start) < ordinal(current):
        raise HTTPException(status_code=422, detail=(
            f"Your plan can't start ({start}) before your current semester ({current})"))


def check_credits(credits: int | None, course: dict) -> int:
    """Default to the course's credits; for variable-credit courses allow its range."""
    if credits is None:
        return course["credits_min"]
    if not course["credits_min"] <= credits <= course["credits_max"]:
        raise HTTPException(
            status_code=422,
            detail=f"Credits must be between {course['credits_min']} and {course['credits_max']}",
        )
    return credits


def touch(conn, session_id: UUID) -> None:
    conn.execute("UPDATE planning_sessions SET updated_at = now() WHERE id = %s", (session_id,))


def load_session(conn, session_id: UUID) -> dict:
    session = conn.execute(
        """
        SELECT s.id, s.reported_credits, s.current_term, s.max_credits_per_term,
               s.plan_start_term, s.target_graduation_term, s.academic_standing,
               s.include_summer, s.max_summer_credits,
               p.slug AS program_slug, p.name AS program_name, u.name AS university
        FROM planning_sessions s
        JOIN programs p ON p.id = s.program_id
        JOIN universities u ON u.id = p.university_id
        WHERE s.id = %s
        """,
        (session_id,),
    ).fetchone()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    courses = conn.execute(
        """
        SELECT c.code, c.name, sc.credits, c.credits_min, c.credits_max, sc.grade,
               sc.status, sc.academic_term_id
        FROM session_courses sc JOIN courses c ON c.id = sc.course_id
        WHERE sc.session_id = %s ORDER BY c.code
        """,
        (session_id,),
    ).fetchall()

    completed = sum(c["credits"] for c in courses
                    if c["status"] == "completed" and c["grade"] != "F")
    reported = session.pop("reported_credits")
    session["courses"] = courses
    session["credits"] = {
        "completed": completed,
        "in_progress": sum(c["credits"] for c in courses if c["status"] == "in_progress"),
        "reported": reported,
        "unmatched": max(reported - completed, 0) if reported is not None else 0,
        "reported_too_low": reported is not None and reported < completed,
    }
    return session
