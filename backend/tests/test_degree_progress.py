"""Tests for the degree progress service.

The first group uses small made-up trees (no database); the second runs the
real UMD Information Science data through the API (needs the seeded database).
"""

import pytest
from fastapi.testclient import TestClient

from app.degree_progress import REPORTED, add_reported_credits, summarize
from app.main import app
from app.evaluator import evaluate, walk


# --- Unit tests on made-up trees -------------------------------------------------

def req(key, rule, eligible=(), children=(), **fields):
    node = {
        "key": key, "name": key, "rule": rule, "category": "major",
        "eligible": list(eligible), "children": list(children),
        "min_courses": None, "min_credits": None, "min_grade": None,
        "allocation_group": None, "optional": False, "any_course": False, **fields,
    }
    node["eligible_courses"] = [
        {"code": c, "name": c, "credits_min": 3, "credits_max": 3} for c in node["eligible"]
    ]
    return node


def taken(*entries):
    return {code: {"code": code, "name": code, "credits": 3, "grade": grade}
            for code, grade in entries}


def run(tree, courses, reported=0):
    add_reported_credits(tree, courses, reported)
    results = evaluate(tree, courses)
    for node in walk(tree):
        node["progress"] = results[node["key"]]
    return summarize(tree, courses)


def keys(units):
    return [u["key"] for u in units]


def sample_tree():
    return [
        req("major", "all_children", allocation_group="major", children=[
            req("core", "all_courses", ["C1", "C2"], allocation_group="major", min_grade="C-"),
            req("electives", "min_credits", ["C1", "C2", "E1", "E2", "E3"], min_credits=6,
                allocation_group="major", min_grade="C-"),
            req("cognate", "min_courses", ["E1", "E2"], min_courses=2, optional=True),
        ]),
        req("degree", "all_children", children=[
            req("total", "min_credits", ["C1", "C2", "E1", "E2", "E3"], min_credits=30,
                any_course=True),
            req("gpa", "not_tracked"),
        ]),
    ]


def test_completed_and_remaining_requirements():
    summary = run(sample_tree(), taken(("C1", "A"), ("C2", "B"), ("E1", "A")))
    assert keys(summary["completed_requirements"]) == ["core"]
    assert keys(summary["remaining_requirements"]) == ["electives", "total"]
    assert keys(summary["untracked_requirements"]) == ["gpa"]


def test_paths_and_optional_requirements():
    summary = run(sample_tree(), taken())
    electives = summary["remaining_requirements"][1]
    assert electives["path"] == ["major"]
    # Optional requirements aren't listed as remaining.
    assert "cognate" not in keys(summary["remaining_requirements"])


def test_credits_remaining():
    summary = run(sample_tree(), taken(("C1", "A"), ("E1", "A")))
    assert summary["credits"] == {"from_courses": 6, "unverified": 0, "counted": 6,
                                  "required": 30, "remaining": 24}
    electives = next(u for u in summary["remaining_requirements"] if u["key"] == "electives")
    assert electives["credits_remaining"] == 3


def test_core_course_does_not_also_count_as_elective():
    summary = run(sample_tree(), taken(("C1", "A"), ("C2", "A")))
    electives = next(u for u in summary["remaining_requirements"] if u["key"] == "electives")
    assert electives["applied_courses"] == []
    assert electives["credits_remaining"] == 6


def test_candidates_exclude_completed_and_courses_named_elsewhere():
    summary = run(sample_tree(), taken(("E1", "A")))
    core = next(u for u in summary["remaining_requirements"] if u["key"] == "core")
    electives = next(u for u in summary["remaining_requirements"] if u["key"] == "electives")
    assert [c["code"] for c in core["candidate_courses"]] == ["C1", "C2"]
    # C1/C2 are named by the core, so they aren't suggested as electives; E1 is done.
    assert [c["code"] for c in electives["candidate_courses"]] == ["E2", "E3"]


def test_low_grade_course_is_a_candidate_to_retake():
    summary = run(sample_tree(), taken(("C1", "D")))
    core = next(u for u in summary["remaining_requirements"] if u["key"] == "core")
    c1 = next(c for c in core["candidate_courses"] if c["code"] == "C1")
    assert c1["earned_grade"] == "D"


def test_missing_grade_counts():
    summary = run(sample_tree(), taken(("C1", None), ("C2", None)))
    assert "core" in keys(summary["completed_requirements"])


def test_reported_credits_count_only_toward_any_course_requirements():
    summary = run(sample_tree(), taken(("C1", "A")), reported=20)
    assert summary["credits"]["counted"] == 23
    assert summary["credits"]["remaining"] == 7
    total = next(u for u in summary["remaining_requirements"] if u["key"] == "total")
    assert total["credits_remaining"] == 7
    assert REPORTED in [c["code"] for c in total["applied_courses"]]
    electives = next(u for u in summary["remaining_requirements"] if u["key"] == "electives")
    assert electives["applied_courses"] == []


def test_any_child_is_one_unit():
    tree = [req("diversity", "any_child", children=[
        req("two_a", "min_courses", ["A1", "A2"], min_courses=2),
        req("a_and_b", "all_children", children=[
            req("one_a", "min_courses", ["A1", "A2"], min_courses=1),
            req("one_b", "min_courses", ["B1"], min_courses=1),
        ]),
    ])]
    summary = run(tree, taken(("A1", "A")))
    [unit] = summary["remaining_requirements"]
    assert unit["key"] == "diversity"
    assert unit["options"] == ["two_a", "a_and_b"]
    assert {c["code"] for c in unit["candidate_courses"]} == {"A2", "B1"}


# --- API tests on the real data ----------------------------------------------------

client = TestClient(app)


@pytest.fixture
def session():
    data = client.post("/api/sessions", json={"program_slug": "umd-information-science",
                                              "reported_credits": 61}).json()
    yield data
    client.delete(f"/api/sessions/{data['id']}")


def add(session, *courses):
    for code, grade in courses:
        response = client.post(f"/api/sessions/{session['id']}/courses",
                               json={"code": code, "grade": grade})
        assert response.status_code == 201


def progress(session):
    response = client.get(f"/api/sessions/{session['id']}/progress")
    assert response.status_code == 200
    return response.json()


def unit(units, key):
    return next(u for u in units if u["key"] == key)


def test_progress_for_new_session(session):
    data = progress(session)
    assert data["program"]["slug"] == "umd-information-science"
    # 61 reported, none matched to courses yet.
    assert data["credits"] == {"from_courses": 0, "unverified": 61, "counted": 61,
                               "required": 120, "remaining": 59}
    assert data["completed_requirements"] == []
    assert "infosci.core" in keys(data["remaining_requirements"])


def test_progress_follows_completed_courses(session):
    add(session, ("MATH115", "A"), ("PSYC100", "B"), ("STAT100", "B"), ("INST126", "A"),
        ("INST201", "A"), ("INST314", "D"), ("INST354", "A"))
    data = progress(session)
    assert data["credits"]["from_courses"] == 21
    assert data["credits"]["remaining"] == 59  # 21 from courses + 40 reported = 61

    assert "infosci.benchmark" in keys(data["completed_requirements"])
    core = unit(data["remaining_requirements"], "infosci.core")
    assert core["courses_remaining"] == 9
    assert {"code": "INST314", "earned_grade": "D"}.items() <= next(
        c for c in core["candidate_courses"] if c["code"] == "INST314").items()

    electives = unit(data["remaining_requirements"], "infosci.electives")
    assert electives["credits_remaining"] == 12
    assert "INST335" not in [c["code"] for c in electives["candidate_courses"]]  # core course

    # INST201 counts for both the major core and Gen Ed (UMD allows that).
    assert "INST201" in [c["code"] for c in core["applied_courses"]]
    dshs = unit(data["completed_requirements"] + data["remaining_requirements"], "umd.gened.dshs")
    assert "INST201" in [c["code"] for c in dshs["applied_courses"]]


def test_removing_a_course_updates_progress(session):
    add(session, ("MATH115", "A"), ("PSYC100", "B"), ("STAT100", "B"), ("INST126", "A"))
    assert "infosci.benchmark" in keys(progress(session)["completed_requirements"])
    client.delete(f"/api/sessions/{session['id']}/courses/INST126")
    assert "infosci.benchmark" in keys(progress(session)["remaining_requirements"])


def test_progress_unknown_session():
    response = client.get("/api/sessions/00000000-0000-0000-0000-000000000000/progress")
    assert response.status_code == 404


def test_suggestions_skip_courses_the_student_cant_take(session):
    add(session, ("INST201", "A"))
    electives = unit(progress(session)["remaining_requirements"], "infosci.electives")
    suggested = {c["code"] for c in electives["candidate_courses"]}
    assert "INST354" in suggested
    # INST301: Shady Grove only, and credit overlaps INST201. INST367: another
    # major. INST363: a minor or permission only.
    assert not {"INST301", "INST367", "INST363"} & suggested
