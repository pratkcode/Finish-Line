from typing import Literal

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.db import get_connection
from app.prerequisites import load_graph, prerequisite_tree

router = APIRouter(prefix="/api/courses", tags=["courses"])

DEFAULT_LIMIT = 200  # search results per request
MAX_LIMIT = 1000


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
    # Where the groups come from: curated | parsed | partial | unstructured | none.
    # "unstructured" means only the official wording is available.
    status: str
    prerequisite_text: str | None
    corequisite_text: str | None


class ConditionalGenEd(BaseModel):
    tag: str
    condition: str  # e.g. "if taken with BSCI161"; not counted toward requirements


class CourseDetail(CourseSummary):
    department: str  # subject code, e.g. "MATH"
    department_name: str | None
    description: str | None
    catalog_year: str | None
    source_url: str | None  # official catalog page
    in_current_catalog: bool
    # Gen Ed tags that count toward requirements (verified on Testudo).
    gen_ed: list[str]
    gen_ed_conditional: list[ConditionalGenEd]  # shown, not counted
    gen_ed_text: str | None  # as listed on Testudo, e.g. "DSHS or DSNS"
    gen_ed_status: Literal["verified", "none_found"]
    gen_ed_term: str | None  # Testudo term the tags came from
    # curated | parsed | partial | unstructured | none (see migration 002)
    prerequisite_status: str
    restriction_text: str | None  # official enrollment restriction
    credit_only_granted_for: str | None  # official wording
    formerly: str | None
    cross_listed_with: str | None
    jointly_offered_with: str | None
    repeatable_to: str | None
    recommended: str | None
    additional_information: str | None
    prerequisites: Prerequisites


class Department(BaseModel):
    code: str
    name: str
    course_count: int


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
def list_courses(
    response: Response,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(pattern=r"^[A-Za-z]{4}$")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
):
    """Search courses by code or name, optionally within one department.
    Codes starting with the search come first. The total number of matches is
    in the X-Total-Count header."""
    where, params = ["in_current_catalog"], {"limit": limit}
    if department:
        where.append("subject = %(department)s")
        params["department"] = department.upper()
    order = "code"
    if search and search.strip():
        where.append("(code ILIKE %(code)s OR name ILIKE %(name)s)")
        code = normalize_code(search)
        params |= {"code": like_pattern(code), "name": like_pattern(search.strip()),
                   "prefix": like_pattern(code)[1:]}
        order = "code ILIKE %(prefix)s DESC, code"
    query = f"""
        SELECT code, name, credits_min, credits_max, count(*) OVER () AS total
        FROM courses WHERE {" AND ".join(where)}
        ORDER BY {order} LIMIT %(limit)s
    """
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    response.headers["X-Total-Count"] = str(rows[0]["total"] if rows else 0)
    return rows


@router.get("/departments", response_model=list[Department], tags=["courses"])
def list_departments():
    """Departments with courses in the current catalog."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT d.code, d.name, count(c.id) AS course_count
            FROM departments d
            JOIN courses c ON c.subject = d.code AND c.university_id = d.university_id
                          AND c.in_current_catalog
            GROUP BY d.code, d.name ORDER BY d.code
            """
        ).fetchall()


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
               c.subject AS department, d.name AS department_name,
               c.description, c.catalog_year, c.source_url, c.in_current_catalog,
               c.prerequisite_text, c.corequisite_text, c.prerequisites_complete,
               c.prerequisite_status, c.gen_ed_text, c.gen_ed_status, c.gen_ed_term,
               c.restriction_text, c.credit_only_granted_for, c.formerly,
               c.cross_listed_with, c.jointly_offered_with, c.repeatable_to, c.recommended,
               c.additional_information,
               COALESCE(array_agg(g.tag ORDER BY g.tag)
                        FILTER (WHERE g.tag IS NOT NULL AND g.condition_text IS NULL), '{}')
                   AS gen_ed,
               COALESCE(json_agg(json_build_object('tag', g.tag, 'condition', g.condition_text))
                        FILTER (WHERE g.condition_text IS NOT NULL), '[]') AS gen_ed_conditional
        FROM courses c
        LEFT JOIN course_gen_ed g ON g.course_id = c.id
        LEFT JOIN departments d ON d.code = c.subject AND d.university_id = c.university_id
        WHERE c.code = %s
        GROUP BY c.id, d.name
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
        "status": course["prerequisite_status"],
        "prerequisite_text": course["prerequisite_text"],
        "corequisite_text": course["corequisite_text"],
    }
