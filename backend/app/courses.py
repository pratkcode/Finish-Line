from typing import Literal

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import get_connection
from app.prerequisites import load_graph, prerequisite_tree

router = APIRouter(prefix="/api/courses", tags=["courses"])


class CourseSummary(BaseModel):
    code: str
    name: str
    credits_min: int
    credits_max: int


class PrerequisiteGroup(BaseModel):
    timing: Literal["before", "before_or_concurrent", "concurrent"]
    min_grade: str | None
    options: list[CourseSummary]  # any one of these satisfies the group


class Prerequisites(BaseModel):
    course_code: str
    # Every group must be satisfied.
    groups: list[PrerequisiteGroup]
    # False when the official text has conditions the groups don't capture.
    complete: bool
    prerequisite_text: str | None
    corequisite_text: str | None


class CourseDetail(CourseSummary):
    description: str | None
    gen_ed: list[str]  # Gen Ed tags, e.g. ["DSHU", "SCIS"]
    gen_ed_text: str | None  # as listed on Testudo, e.g. "DSHS or DSNS"
    restriction_text: str | None  # official enrollment restriction
    credit_only_granted_for: str | None  # official wording
    prerequisites: Prerequisites


class Dependent(CourseSummary):
    timing: Literal["before", "before_or_concurrent", "concurrent"]
    min_grade: str | None
    alternatives: list[str]  # other courses that satisfy the same prerequisite group


def normalize_code(code: str) -> str:
    # Accept "inst326" and "INST 326".
    return code.replace(" ", "").upper()


def like_pattern(text: str) -> str:
    """Substring pattern for ILIKE, with the user's % and _ matched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", response_model=list[CourseSummary])
def list_courses(search: Annotated[str | None, Query(max_length=100)] = None):
    """List courses, optionally filtered by code or name."""
    query = "SELECT code, name, credits_min, credits_max FROM courses"
    params = {}
    if search and search.strip():
        query += " WHERE code ILIKE %(code)s OR name ILIKE %(name)s"
        params = {"code": like_pattern(normalize_code(search)), "name": like_pattern(search.strip())}
    query += " ORDER BY code"

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


@router.get("/{course_code}", response_model=CourseDetail)
def get_course(course_code: str):
    with get_connection() as conn:
        course = find_course(conn, course_code)
        return {**course, "prerequisites": load_prerequisites(conn, course)}


@router.get("/{course_code}/prerequisites", response_model=Prerequisites)
def get_prerequisites(course_code: str):
    with get_connection() as conn:
        course = find_course(conn, course_code)
        return load_prerequisites(conn, course)


class PrerequisiteTreeGroup(BaseModel):
    timing: Literal["before", "before_or_concurrent", "concurrent"]
    min_grade: str | None
    options: list["PrerequisiteTree"]


class PrerequisiteTree(CourseSummary):
    prerequisites_complete: bool
    cycle: bool  # True if this course already appears above it (not expanded)
    groups: list[PrerequisiteTreeGroup]


@router.get("/{course_code}/prerequisite-tree", response_model=PrerequisiteTree)
def get_prerequisite_tree(course_code: str):
    """Every level of prerequisites below a course."""
    with get_connection() as conn:
        course = find_course(conn, course_code)
        graph = load_graph(conn, course["university_id"])
    return prerequisite_tree(graph, course["code"])


@router.get("/{course_code}/dependents", response_model=list[Dependent])
def get_dependents(course_code: str):
    """Courses that list this course as a prerequisite (what it unlocks)."""
    with get_connection() as conn:
        course = find_course(conn, course_code)
        return conn.execute(
            """
            SELECT c.code, c.name, c.credits_min, c.credits_max, g.timing, g.min_grade,
                   COALESCE(array_agg(other.code ORDER BY other.code)
                            FILTER (WHERE other.id <> %(id)s), '{}') AS alternatives
            FROM prerequisite_options mine
            JOIN prerequisite_groups g ON g.id = mine.group_id
            JOIN courses c ON c.id = g.course_id
            JOIN prerequisite_options o ON o.group_id = g.id
            JOIN courses other ON other.id = o.course_id
            WHERE mine.course_id = %(id)s
            GROUP BY c.id, g.id
            ORDER BY c.code
            """,
            {"id": course["id"]},
        ).fetchall()


def find_course(conn, course_code: str) -> dict:
    course = conn.execute(
        """
        SELECT c.id, c.university_id, c.code, c.name, c.credits_min, c.credits_max,
               c.description, c.prerequisite_text, c.corequisite_text,
               c.prerequisites_complete, c.gen_ed_text, c.restriction_text,
               c.credit_only_granted_for,
               array_remove(array_agg(g.tag ORDER BY g.tag), NULL) AS gen_ed
        FROM courses c LEFT JOIN course_gen_ed g ON g.course_id = c.id
        WHERE c.code = %s
        GROUP BY c.id
        """,
        (normalize_code(course_code),),
    ).fetchone()
    if course is None:
        raise HTTPException(status_code=404, detail=f"Course {course_code} not found")
    return course


def load_prerequisites(conn, course: dict) -> dict:
    rows = conn.execute(
        """
        SELECT g.id AS group_id, g.timing, g.min_grade,
               c.code, c.name, c.credits_min, c.credits_max
        FROM prerequisite_groups g
        JOIN prerequisite_options o ON o.group_id = g.id
        JOIN courses c ON c.id = o.course_id
        WHERE g.course_id = %s
        ORDER BY g.id, c.code
        """,
        (course["id"],),
    ).fetchall()

    groups = {}
    for row in rows:
        group = groups.setdefault(
            row["group_id"],
            {"timing": row["timing"], "min_grade": row["min_grade"], "options": []},
        )
        group["options"].append(row)

    return {
        "course_code": course["code"],
        "groups": list(groups.values()),
        "complete": course["prerequisites_complete"],
        "prerequisite_text": course["prerequisite_text"],
        "corequisite_text": course["corequisite_text"],
    }
