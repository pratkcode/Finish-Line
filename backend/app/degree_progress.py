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
from app.student_record import load_student_record, taken_courses

router = APIRouter(prefix="/api/sessions", tags=["degree progress"])

# Stand-in "course" for verified credit that doesn't map to a specific UMD
# course (e.g. transfer elective credit). It only counts toward requirements
# where any course counts, such as the 120-credit total.
REPORTED = "TRANSFER-CREDIT"


class CandidateCourse(BaseModel):
    code: str
    name: str
    credits_min: int
    credits_max: int
    # Set when the student took the course but the grade was too low to count.
    earned_grade: str | None = None
    # Set when you reported transfer credit for this course that UMD hasn't verified.
    pending_transfer: str | None = None


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
    # Courses that could still satisfy it: the first MAX_CANDIDATES (verified
    # prerequisites first), plus the total. Empty when any course counts.
    candidate_courses: list[CandidateCourse]
    candidate_count: int
    # "Complete one of" requirements list their options here.
    options: list[str]
    fulfilled: bool  # met by a verified transfer evaluation, waiver, ... (not courses)
    in_progress_courses: list[str]  # courses you're taking that will count when finished


class CreditSummary(BaseModel):
    earned: int  # all completed credit recorded, verified or not
    applicable: int  # completed credit that counts toward the degree
    from_courses: int  # part of applicable: UMD courses and verified course equivalents
    credit_block: int  # part of applicable: verified credit without a specific course
    unverified: int  # recorded but not counted (student-reported, pending verification)
    in_progress: int  # credits you're taking now (not counted yet)
    required: int | None  # degree total, from the requirement data
    remaining: int | None  # required - applicable


class PendingItem(BaseModel):
    kind: str
    description: str
    credits: int
    reason: str


class DegreeProgress(BaseModel):
    session_id: UUID
    program: Program
    credits: CreditSummary
    completed_requirements: list[RequirementSummary]
    remaining_requirements: list[RequirementSummary]
    untracked_requirements: list[RequirementSummary]
    pending: list[PendingItem]  # recorded but not counted, and why
    requirements: list[Requirement]  # full tree with progress, for detail views


@router.get("/{session_id}/progress", response_model=DegreeProgress)
def get_degree_progress(session_id: UUID):
    with get_connection() as conn:
        return calculate_degree_progress(conn, session_id)


def calculate_degree_progress(conn, session_id: UUID) -> dict:
    session = load_session(conn, session_id)
    program = find_program(conn, session["program_slug"])
    tree, courses = load_requirements(conn, program)
    record = load_student_record(conn, session_id, session)

    taken = taken_courses(record, courses)
    add_reported_credits(tree, taken, record.credit_block)
    results = evaluate(tree, taken, record.fulfilled)
    for node in walk(tree):
        node["progress"] = results[node["key"]]
    summary = summarize(tree, taken, load_rules(conn, program))

    # Which in-progress courses would count, once finished.
    with_in_progress = evaluate(tree, {**taken, **taken_courses(record, courses, True)},
                                record.fulfilled)
    nodes = {node["key"]: node for node in walk(tree)}
    units = (summary["completed_requirements"] + summary["remaining_requirements"]
             + summary["untracked_requirements"])
    verified = {code for code, c in courses.items() if c["verified_prerequisites"]}
    for unit in units:
        later = applied_codes(nodes[unit["key"]], with_in_progress)
        unit["in_progress_courses"] = sorted(c for c in later if c in record.in_progress)
        unit["candidate_courses"] = [c for c in unit["candidate_courses"]
                                     if c["code"] not in record.in_progress]
        for c in unit["candidate_courses"]:
            c["pending_transfer"] = record.reported_equivalents.get(c["code"])
        cap_candidates(unit, verified)

    credits = summary["credits"]
    credits |= {"earned": record.earned_credits,
                "unverified": record.unverified_credits,
                "in_progress": record.in_progress_credits}
    return {"session_id": session_id, "program": program, "requirements": tree,
            "pending": record.pending, **summary}


def applied_codes(node: dict, results: dict) -> set[str]:
    """Courses applied to a requirement (or any requirement under it) in `results`."""
    return {c["code"] for n in walk([node]) for c in results[n["key"]]["applied_courses"]}


MAX_CANDIDATES = 40


def cap_candidates(unit: dict, verified: set[str]) -> None:
    """Keep responses small: list at most MAX_CANDIDATES suggestions, verified
    prerequisites and retakes first, and report how many there are in total."""
    candidates = unit["candidate_courses"]
    unit["candidate_count"] = len(candidates)
    if len(candidates) > MAX_CANDIDATES:
        candidates.sort(key=lambda c: (not c["earned_grade"], c["code"] not in verified, c["code"]))
        unit["candidate_courses"] = candidates[:MAX_CANDIDATES]


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

    from_courses = sum(c["credits"] for code, c in taken.items()
                       if code != REPORTED and c["grade"] != "F")
    credit_block = taken[REPORTED]["credits"] if REPORTED in taken else 0
    counted = from_courses + credit_block
    total = [n["min_credits"] for n in walk(tree) if n.get("any_course") and n["min_credits"]]
    required = max(total) if total else None
    return {
        "credits": {
            "from_courses": from_courses,
            "credit_block": credit_block,
            "applicable": counted,
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
        "fulfilled": progress.get("fulfilled", False),
        "in_progress_courses": [],
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
