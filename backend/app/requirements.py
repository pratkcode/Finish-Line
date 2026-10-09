from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import get_connection
from app.courses import CourseSummary
from app.evaluator import Grade, evaluate, walk

router = APIRouter(prefix="/api/programs", tags=["requirements"])

Status = Literal["complete", "in_progress", "not_started", "not_tracked"]


class Program(BaseModel):
    slug: str
    name: str
    university: str


class CourseFilter(BaseModel):
    subject: str | None
    min_number: int | None
    max_number: int | None
    gen_ed: str | None


class AppliedCourse(BaseModel):
    code: str
    name: str
    credits: int
    grade: Grade | None  # None = not entered


class Progress(BaseModel):
    status: Status
    applied_courses: list[AppliedCourse]  # student courses counted here
    credits_completed: int
    courses_remaining: int | None
    credits_remaining: int | None


class Requirement(BaseModel):
    key: str
    name: str
    description: str | None
    category: str
    rule: str
    optional: bool
    min_courses: int | None
    min_credits: int | None
    min_grade: str | None
    source_url: str | None
    courses: list[CourseSummary]  # courses listed by name in the requirement
    filters: list[CourseFilter]  # patterns that match more courses
    # Courses that can satisfy it: the first MAX_LISTED (verified prerequisites
    # first), plus the total. Empty when any course counts.
    eligible_courses: list[CourseSummary]
    eligible_count: int
    progress: Progress | None = None
    children: list["Requirement"]


class RequirementsResponse(BaseModel):
    program: Program
    requirements: list[Requirement]


class TakenCourse(BaseModel):
    code: str
    grade: Grade | None = None  # None = not entered; assumed to meet minimums
    credits: int | None = Field(None, description="Only needed for variable-credit courses")


class ProgressRequest(BaseModel):
    courses: list[TakenCourse]


class ProgressResponse(RequirementsResponse):
    unrecognized_courses: list[str]  # codes not in the course database


@router.get("", response_model=list[Program])
def list_programs():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT p.slug, p.name, u.name AS university
            FROM programs p JOIN universities u ON u.id = p.university_id
            ORDER BY u.name, p.name
            """
        ).fetchall()


@router.get("/{slug}/requirements", response_model=RequirementsResponse)
def get_requirements(slug: str):
    with get_connection() as conn:
        program = find_program(conn, slug)
        tree, _ = load_requirements(conn, program)
    return {"program": program, "requirements": tree}


@router.post("/{slug}/progress", response_model=ProgressResponse)
def get_progress(slug: str, body: ProgressRequest):
    """Check a list of completed courses against the program's requirements."""
    with get_connection() as conn:
        program = find_program(conn, slug)
        tree, courses = load_requirements(conn, program)

    taken, unrecognized = {}, []
    for entry in body.courses:
        code = entry.code.replace(" ", "").upper()
        course = courses.get(code)
        if course is None:
            unrecognized.append(code)
            continue
        credits = entry.credits or course["credits_min"]
        taken[code] = {"code": code, "name": course["name"], "credits": credits,
                       "grade": entry.grade}

    results = evaluate(tree, taken)
    for node in walk(tree):
        node["progress"] = results[node["key"]]
    return {"program": program, "requirements": tree, "unrecognized_courses": unrecognized}


def find_program(conn, slug: str) -> dict:
    program = conn.execute(
        """
        SELECT p.id, p.university_id, p.slug, p.name, u.name AS university
        FROM programs p JOIN universities u ON u.id = p.university_id
        WHERE p.slug = %s
        """,
        (slug,),
    ).fetchone()
    if program is None:
        raise HTTPException(status_code=404, detail=f"Program {slug} not found")
    return program


def load_requirements(conn, program: dict) -> tuple[list[dict], dict]:
    """Build the requirement tree for a program: its own requirements first,
    then its university's. Returns (tree, courses by code)."""
    rows = conn.execute(
        """
        WITH RECURSIVE tree AS (
            -- path sorts the program's own requirements first, and every
            -- parent before its children.
            SELECT r.*, ARRAY[CASE WHEN r.program_id IS NOT NULL THEN 0 ELSE 1 END,
                              r.sort_order] AS path
            FROM requirements r
            WHERE r.program_id = %(program_id)s OR r.university_id = %(university_id)s
            UNION ALL
            SELECT r.*, tree.path || r.sort_order
            FROM requirements r JOIN tree ON r.parent_id = tree.id
        )
        SELECT * FROM tree ORDER BY path
        """,
        {"program_id": program["id"], "university_id": program["university_id"]},
    ).fetchall()
    ids = [row["id"] for row in rows]

    courses = {}
    for course in conn.execute(
        """
        SELECT c.code, c.name, c.credits_min, c.credits_max, c.subject, c.number,
               c.prerequisite_status IN ('curated', 'parsed', 'none')
                   AND c.prerequisites_complete AS verified_prerequisites,
               -- Only unconditional, verified Gen Ed tags count toward requirements.
               COALESCE(array_agg(g.tag) FILTER (WHERE g.tag IS NOT NULL
                                                  AND g.condition_text IS NULL), '{}') AS gen_ed
        FROM courses c LEFT JOIN course_gen_ed g ON g.course_id = c.id
        WHERE c.university_id = %s
        GROUP BY c.id ORDER BY c.code
        """,
        (program["university_id"],),
    ).fetchall():
        courses[course["code"]] = course

    listed = {}
    for row in conn.execute(
        """
        SELECT rc.requirement_id, c.code FROM requirement_courses rc
        JOIN courses c ON c.id = rc.course_id
        WHERE rc.requirement_id = ANY(%s) ORDER BY c.code
        """,
        (ids,),
    ).fetchall():
        listed.setdefault(row["requirement_id"], []).append(row["code"])

    filters = {}
    for row in conn.execute(
        """
        SELECT requirement_id, subject, min_number, max_number, gen_ed
        FROM requirement_course_filters WHERE requirement_id = ANY(%s) ORDER BY id
        """,
        (ids,),
    ).fetchall():
        filters.setdefault(row.pop("requirement_id"), []).append(row)

    nodes = {}
    roots = []
    for row in rows:
        listed_codes = listed.get(row["id"], [])
        node_filters = filters.get(row["id"], [])
        eligible = eligible_codes(row["rule"], listed_codes, node_filters, courses)
        node = {
            **{k: row[k] for k in ("key", "name", "description", "category", "rule", "optional",
                                   "min_courses", "min_credits", "min_grade", "allocation_group",
                                   "source_url")},
            "courses": [courses[code] for code in listed_codes],
            "filters": node_filters,
            "eligible": eligible,
            # True when every course counts (e.g. "120 total credits").
            "any_course": row["rule"] in ("min_courses", "min_credits")
                          and not listed_codes and not node_filters,
            "eligible_courses": listed_courses(eligible, courses, row["rule"], listed_codes,
                                               node_filters),
            "eligible_count": len(eligible),
            "children": [],
        }
        nodes[row["id"]] = node
        if row["parent_id"] is None:
            roots.append(node)
        else:
            nodes[row["parent_id"]]["children"].append(node)
    return roots, courses


MAX_LISTED = 50


def listed_courses(eligible: list[str], courses: dict, rule: str, listed: list[str],
                   filters: list[dict]) -> list[dict]:
    """The courses to show for a requirement. Large pattern-based sets (Gen Ed,
    upper-level) are capped; courses with verified prerequisites come first."""
    if rule in ("min_courses", "min_credits") and not listed and not filters:
        return []  # any course counts, e.g. "120 total credits"
    if len(eligible) <= MAX_LISTED:
        return [courses[code] for code in eligible]
    ranked = sorted(eligible, key=lambda code: (not courses[code]["verified_prerequisites"], code))
    return [courses[code] for code in ranked[:MAX_LISTED]]


def eligible_codes(rule: str, listed: list[str], filters: list[dict], courses: dict) -> list[str]:
    if rule in ("all_children", "any_child", "not_tracked"):
        return []
    if not listed and not filters:
        return list(courses)  # e.g. "120 total credits": every course counts
    matched = [code for code, course in courses.items()
               if code not in listed and any(matches(course, f) for f in filters)]
    return listed + matched


def matches(course: dict, f: dict) -> bool:
    return (
        (f["subject"] is None or course["subject"] == f["subject"])
        and (f["min_number"] is None or course["number"] >= f["min_number"])
        and (f["max_number"] is None or course["number"] <= f["max_number"])
        and (f["gen_ed"] is None or f["gen_ed"] in course["gen_ed"])
    )
