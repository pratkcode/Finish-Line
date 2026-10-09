"""Planning across UMD departments with only verified data (needs the migrated, seeded database)."""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]
SLUG = "umd-information-science"


@pytest.fixture
def session():
    data = client.post("/api/sessions", json={
        "program_slug": SLUG, "current_term": "Fall 2026", "max_credits_per_term": 15}).json()
    yield data
    client.delete(f"/api/sessions/{data['id']}")


def add(session, *codes, grade="B"):
    for code in codes:
        response = client.post(f"/api/sessions/{session['id']}/courses",
                               json={"code": code, "grade": grade})
        assert response.status_code == 201, (code, response.text)


def get(session, path):
    response = client.get(f"/api/sessions/{session['id']}/{path}")
    assert response.status_code == 200
    return response.json()


def requirement(progress, key):
    units = (progress["completed_requirements"] + progress["remaining_requirements"]
             + progress["untracked_requirements"])
    return next(u for u in units if u["key"] == key)


def counted_gen_ed(code):
    return set(client.get(f"/api/courses/{code}").json()["gen_ed"])


# --- Catalog -----------------------------------------------------------------

def test_catalog_spans_departments_without_duplicates():
    departments = client.get("/api/courses/departments").json()
    assert len(departments) > 150
    with get_connection() as conn:
        row = conn.execute("SELECT count(*) AS total, "
                           "count(DISTINCT (university_id, code)) AS distinct_codes FROM courses").fetchone()
    total, distinct = row["total"], row["distinct_codes"]
    assert total == distinct > 5000


def test_search_across_and_within_departments():
    response = client.get("/api/courses", params={"search": "statistics"})
    departments = {c["code"][:4] for c in response.json()}
    assert {"STAT", "INST"} <= departments and len(departments) >= 4
    stat = client.get("/api/courses", params={"department": "STAT"}).json()
    assert stat and all(c["code"].startswith("STAT") for c in stat)


def test_course_detail_reports_data_status():
    course = client.get("/api/courses/CMSC250").json()
    assert course["department_name"] == "Computer Science"
    assert course["catalog_year"] == "2026-2027"
    assert course["source_url"].startswith("https://academiccatalog.umd.edu/")
    assert course["prerequisite_status"] == "parsed"
    unstructured = client.get("/api/courses/ENGL391").json()
    assert unstructured["prerequisites"]["status"] == "unstructured"
    assert unstructured["prerequisites"]["complete"] is False
    assert unstructured["prerequisites"]["groups"] == []


# --- Degree calculations use non-INST courses ------------------------------------

def test_non_inst_courses_satisfy_requirements(session):
    add(session, "ENGL101", "COMM107", "MATH115", "CMSC131")
    progress = get(session, "progress")
    assert requirement(progress, "umd.gened.fsaw")["status"] == "complete"
    assert requirement(progress, "umd.gened.fsoc")["status"] == "complete"
    assert requirement(progress, "umd.gened.fsma")["status"] == "complete"
    # CMSC131 carries no Gen Ed tag: it only counts toward total credits.
    total = requirement(progress, "umd.degree.total_credits")
    assert "CMSC131" in [c["code"] for c in total["applied_courses"]]
    for unit in progress["completed_requirements"] + progress["remaining_requirements"]:
        if unit["key"] != "umd.degree.total_credits":
            assert "CMSC131" not in [c["code"] for c in unit["applied_courses"]]


def test_conditional_gen_ed_tags_are_not_counted(session):
    # BSCI160: "DSNL (if taken with BSCI180) or DSNS". The lab condition can't be
    # checked, so only DSNS counts.
    add(session, "BSCI160")
    progress = get(session, "progress")
    assert requirement(progress, "umd.gened.dsnl")["status"] != "complete"
    assert "BSCI160" in [c["code"] for c in requirement(progress, "umd.gened.dsns")["applied_courses"]]


def test_parsed_prerequisites_block_non_inst_courses(session):
    add(session, "CMSC131")
    cmsc250 = get(session, "eligibility/CMSC250")
    assert cmsc250["status"] == "blocked"
    # CMSC250 <- MATH141 <- MATH140, all parsed from the catalog wording. MATH140's own
    # prerequisite (placement) is text only, so the chain stops there.
    assert [c["code"] for c in cmsc250["complete_first"]] == ["MATH140", "MATH141"]
    missing = [g for g in cmsc250["groups"] if g["state"] == "missing"]
    assert [[o["code"] for o in g["options"]] for g in missing] == [["MATH141"]]


def test_unverified_prerequisites_are_flagged_not_assumed(session):
    english = get(session, "eligibility/ENGL391")
    assert english["groups"] == []
    assert "Academic Writing" in english["additional_conditions"]


def test_unknown_codes_are_not_counted():
    response = client.post(f"/api/programs/{SLUG}/progress", json={"courses": [
        {"code": "ZZZZ999", "grade": "A"}, {"code": "ENGL101", "grade": "A"}]})
    data = response.json()
    assert data["unrecognized_courses"] == ["ZZZZ999"]


# --- Planning with INST and non-INST courses ---------------------------------------

def test_plan_mixes_inst_and_verified_non_inst_courses(session):
    add(session, "ENGL101", "MATH115", "PSYC100", "STAT100", "INST126", "INST201")
    plan = get(session, "plan")
    assert plan["unscheduled"] == [] and plan["unplanned_requirements"] == []
    assert plan["projected_graduation"]
    planned = [c for t in plan["terms"] for c in t["courses"] if c["code"]]
    codes = [c["code"] for c in planned]
    assert any(c.startswith("INST") for c in codes)
    non_inst = [c for c in planned if not c["code"].startswith("INST")]
    assert non_inst, "Gen Ed should be planned with real courses from other departments"

    gen_ed_keys = {"umd.gened.fspw": "FSPW", "umd.gened.fsoc": "FSOC", "umd.gened.dshu": "DSHU",
                   "umd.gened.dsnl": "DSNL", "umd.gened.dssp": "DSSP", "umd.gened.dshs": "DSHS",
                   "umd.gened.big_question": "SCIS"}
    for course in non_inst:
        detail = client.get(f"/api/courses/{course['code']}").json()
        assert detail["in_current_catalog"]
        for fills in course["satisfies"]:
            tag = gen_ed_keys.get(fills["key"])
            if tag:
                # Each Gen Ed it fills is a verified, unconditional tag.
                assert tag in detail["gen_ed"], (course["code"], tag)

    # Credit limit and prerequisite order hold across departments.
    where = {c["code"]: i for i, t in enumerate(plan["terms"]) for c in t["courses"] if c["code"]}
    for t in plan["terms"]:
        assert t["credits"] <= 15
    for code, index in where.items():
        for group in client.get(f"/api/courses/{code}/prerequisites").json()["groups"]:
            planned_options = [o["code"] for o in group["options"] if o["code"] in where]
            if planned_options and group["timing"] == "before":
                assert min(where[o] for o in planned_options) < index, code


def test_planner_never_uses_courses_outside_the_current_catalog(session):
    add(session, "ENGL101", "MATH115", "PSYC100", "STAT100", "INST126", "INST201")
    first = get(session, "plan")
    candidates = [c["code"] for t in first["terms"] for c in t["courses"]
                  if c["code"] and not c["code"].startswith("INST")]
    retired = candidates[0]
    with get_connection() as conn:
        conn.execute("UPDATE courses SET in_current_catalog = FALSE WHERE code = %s", (retired,))
    try:
        second = get(session, "plan")
        assert retired not in [c["code"] for t in second["terms"] for c in t["courses"]]
    finally:
        with get_connection() as conn:
            conn.execute("UPDATE courses SET in_current_catalog = TRUE WHERE code = %s", (retired,))


def test_planner_uses_parsed_credit_standing_for_non_inst_courses(session):
    # ENGL391-398 (Professional Writing) require 60 earned credits.
    add(session, "ENGL101", "MATH115", "PSYC100", "STAT100", "INST126", "INST201")
    plan = get(session, "plan")
    earned = 18
    for t in plan["terms"]:
        for c in t["courses"]:
            if c["code"] and c["code"].startswith("ENGL39"):
                assert earned >= 60
                assert "Requires 60 earned credits" in c["notes"]
        earned += t["credits"]


# --- Data sync keeps student records ---------------------------------------------

def test_sync_preserves_students_and_course_ids(session):
    add(session, "ENGL101", "INST126")
    client.put(f"/api/sessions/{session['id']}/plan/overrides",
               json={"pinned": [{"code": "COMM107", "term": "Spring 2027"}], "removed": []})
    with get_connection() as conn:
        before = conn.execute(
            "SELECT c.code, c.id FROM session_courses s JOIN courses c ON c.id = s.course_id "
            "WHERE s.session_id = %s ORDER BY c.code", (session["id"],)).fetchall()

    result = subprocess.run([sys.executable, str(ROOT / "database" / "migrate.py")],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr

    with get_connection() as conn:
        after = conn.execute(
            "SELECT c.code, c.id FROM session_courses s JOIN courses c ON c.id = s.course_id "
            "WHERE s.session_id = %s ORDER BY c.code", (session["id"],)).fetchall()
        duplicates = conn.execute(
            "SELECT count(*) - count(DISTINCT code) AS n FROM courses").fetchone()["n"]
    assert before == after
    assert duplicates == 0
    assert get(session, "plan")["pinned"] == [{"code": "COMM107", "term": "Spring 2027"}]
