"""The student's saved semester plan and switching majors (needs the migrated database)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
INFOSCI = "umd-information-science"
TID = "umd-technology-info-design"
UNVERIFIED = "umd-computer-science"


@pytest.fixture
def session():
    data = client.post("/api/sessions", json={
        "program_slug": INFOSCI, "current_term": "Fall 2026", "max_credits_per_term": 15}).json()
    for code in ["ENGL101", "MATH115", "PSYC100", "STAT100", "INST126", "INST201", "SOCY105"]:
        client.post(f"/api/sessions/{data['id']}/courses", json={"code": code, "grade": "B"})
    yield data
    client.delete(f"/api/sessions/{data['id']}")


def url(session, path=""):
    return f"/api/sessions/{session['id']}/plan{path}"


def add(session, code, term, **extra):
    return client.post(url(session, "/courses"), json={"code": code, "term": term, **extra})


def term_credits(plan):
    return {t["term"]: t["credits"] for t in plan["terms"]}


def term_codes(plan):
    return {t["term"]: [c["code"] for c in t["courses"]] for t in plan["terms"]}


# --- Credits come from the saved courses ----------------------------------------------

def test_new_plan_is_empty(session):
    plan = client.get(url(session)).json()
    assert plan["terms"] == []
    assert plan["credits"]["planned"] == 0
    assert plan["projected_graduation"] is None
    assert "empty" in plan["graduation_note"]
    assert plan["credits"]["completed"] == 21


def test_adding_courses_increases_totals(session):
    assert add(session, "INST326", "Fall 2026").status_code == 201
    plan = add(session, "INST327", "Fall 2026").json()
    assert term_credits(plan) == {"Fall 2026": 6}
    assert plan["credits"] == {"completed": 21, "planned": 6, "total": 27, "required": 120,
                               "remaining": 93}


def test_removing_a_course_decreases_totals_immediately(session):
    add(session, "INST326", "Fall 2026")
    add(session, "INST327", "Fall 2026")
    add(session, "INST311", "Spring 2027")
    response = client.delete(url(session, "/courses/INST327"))
    assert response.status_code == 200
    plan = response.json()
    assert term_credits(plan) == {"Fall 2026": 3, "Spring 2027": 3}
    assert plan["credits"]["planned"] == 6
    assert plan["credits"]["remaining"] == 93
    # Nothing was put back in its place.
    assert term_codes(plan) == {"Fall 2026": ["INST326"], "Spring 2027": ["INST311"]}


def test_removing_the_last_course_in_a_semester_removes_the_semester(session):
    add(session, "INST326", "Fall 2026")
    plan = client.delete(url(session, "/courses/INST326")).json()
    assert plan["terms"] == [] and plan["credits"]["planned"] == 0


def test_moving_keeps_total_and_shifts_semester_credits(session):
    add(session, "INST326", "Fall 2026")
    add(session, "INST311", "Fall 2026")
    add(session, "INST327", "Spring 2027")
    before = client.get(url(session)).json()
    plan = client.patch(url(session, "/courses/INST311"), json={"term": "Spring 2027"}).json()
    assert term_credits(before) == {"Fall 2026": 6, "Spring 2027": 3}
    assert term_credits(plan) == {"Fall 2026": 3, "Spring 2027": 6}
    assert plan["credits"]["planned"] == before["credits"]["planned"] == 9


def test_variable_credit_courses(session):
    plan = add(session, "INST408", "Spring 2027", credits=2).json()
    assert term_credits(plan) == {"Spring 2027": 2}
    plan = client.patch(url(session, "/courses/INST408"), json={"credits": 4}).json()
    assert plan["credits"]["planned"] == 4
    assert add(session, "INST326", "Fall 2026", credits=4).status_code == 422  # fixed 3 credits
    assert client.patch(url(session, "/courses/INST408"), json={"credits": 9}).status_code == 422


def test_retake_does_not_count_credits_twice(session):
    client.post(f"/api/sessions/{session['id']}/courses", json={"code": "INST314", "grade": "D"})
    plan = add(session, "INST314", "Fall 2026").json()
    [course] = plan["terms"][0]["courses"]
    assert course["retake"] is True
    assert plan["terms"][0]["credits"] == 3  # the semester's load
    assert plan["credits"]["planned"] == 0  # no new credits toward 120


def test_plan_is_saved_and_reloads(session):
    add(session, "INST326", "Fall 2026")
    add(session, "INST346", "Spring 2027")
    client.patch(url(session, "/courses/INST346"), json={"term": "Fall 2027"})
    reloaded = TestClient(app).get(url(session)).json()  # a fresh client, like a page reload
    assert term_codes(reloaded) == {"Fall 2026": ["INST326"], "Fall 2027": ["INST346"]}
    assert reloaded["credits"]["planned"] == 6


def test_clear_plan(session):
    add(session, "INST326", "Fall 2026")
    plan = client.delete(url(session)).json()
    assert plan["terms"] == []


# --- Validation ------------------------------------------------------------------------

def test_duplicates_and_invalid_courses_are_rejected(session):
    add(session, "INST326", "Fall 2026")
    assert add(session, "INST326", "Spring 2027").status_code == 409  # already planned
    assert add(session, "INST201", "Spring 2027").status_code == 409  # already completed
    assert add(session, "ZZZZ999", "Fall 2026").status_code == 404
    assert add(session, "INST327", "Spring 2026").status_code == 422  # before the current term
    assert add(session, "INST327", "Summer 2027").status_code == 422  # Fall/Spring only
    assert client.delete(url(session, "/courses/INST327")).status_code == 404
    assert client.patch(url(session, "/courses/INST327"), json={"term": "Fall 2027"}).status_code == 404


def test_prerequisite_order_is_checked(session):
    add(session, "INST346", "Fall 2026")  # needs INST326 and INST327 first
    plan = add(session, "INST326", "Spring 2027").json()
    messages = [w["message"] for w in plan["warnings"] if w["code"] == "INST346"]
    assert "Needs INST326 first, but INST326 is planned for Spring 2027." in messages
    assert "Needs INST327 first, and it isn't in your plan." in messages
    # Fixing the order removes those warnings.
    add(session, "INST327", "Fall 2026")
    client.patch(url(session, "/courses/INST326"), json={"term": "Fall 2026"})
    plan = client.patch(url(session, "/courses/INST346"), json={"term": "Spring 2027"}).json()
    assert not [w for w in plan["warnings"] if w["code"] == "INST346" and "Needs" in w["message"]]


def test_credit_limit_is_checked(session):
    for code in ["INST311", "INST314", "INST326", "INST327", "INST335"]:
        add(session, code, "Fall 2026")
    plan = add(session, "INST354", "Fall 2026").json()
    fall = plan["terms"][0]
    assert fall["credits"] == 18
    assert fall["warnings"] == ["18 credits is over your 15-credit limit."]


def test_degree_requirements_are_checked(session):
    plan = add(session, "INST326", "Fall 2026").json()
    [course] = plan["terms"][0]["courses"]
    assert "Major Core Requirements" in [s["name"] for s in course["satisfies"]]
    # A course restricted to another major is flagged.
    plan = add(session, "INST380", "Fall 2026").json()
    inst380 = next(c for c in plan["terms"][0]["courses"] if c["code"] == "INST380")
    assert "Restricted to other programs." in inst380["warnings"]
    # Requirements not yet covered are listed.
    assert "infosci.core" in [u["key"] for u in plan["still_needed"]]


# --- Recommendations are optional ------------------------------------------------------

def test_recommendation_is_not_saved_until_accepted(session):
    add(session, "INST326", "Fall 2026")
    rec = client.post(url(session, "/recommendation")).json()
    assert "recommendation" in rec["disclaimer"]
    assert rec["additions"] and "INST326" not in [c["code"] for c in rec["additions"]]
    assert term_codes(client.get(url(session)).json()) == {"Fall 2026": ["INST326"]}

    chosen = rec["additions"][:3]
    plan = client.post(url(session, "/recommendation/accept"), json={
        "courses": [{"code": c["code"], "term": c["term"]} for c in chosen]}).json()
    codes = [c["code"] for t in plan["terms"] for c in t["courses"]]
    assert sorted(codes) == sorted(["INST326"] + [c["code"] for c in chosen])
    assert plan["credits"]["planned"] == 3 + sum(c["credits"] for c in chosen)


def test_accepted_plan_stays_editable(session):
    rec = client.post(url(session, "/recommendation")).json()
    client.post(url(session, "/recommendation/accept"), json={
        "courses": [{"code": c["code"], "term": c["term"]} for c in rec["additions"]]})
    first = rec["additions"][0]
    before = client.get(url(session)).json()["credits"]["planned"]
    after = client.delete(url(session, f"/courses/{first['code']}")).json()["credits"]["planned"]
    assert after == before - first["credits"]


# --- Switching majors ------------------------------------------------------------------

def progress_keys(session):
    progress = client.get(f"/api/sessions/{session['id']}/progress").json()
    return {u["key"] for k in ("completed_requirements", "remaining_requirements")
            for u in progress[k]}, progress


def test_switching_between_supported_majors(session):
    add(session, "INST380", "Fall 2026")
    infosci_keys, _ = progress_keys(session)
    assert "infosci.core" in infosci_keys

    response = client.patch(f"/api/sessions/{session['id']}", json={"program_slug": TID})
    assert response.status_code == 200
    assert response.json()["program_slug"] == TID
    # Completed courses and the plan are kept.
    assert [c["code"] for c in response.json()["courses"]] == [
        "ENGL101", "INST126", "INST201", "MATH115", "PSYC100", "SOCY105", "STAT100"]
    plan = client.get(url(session)).json()
    assert term_codes(plan) == {"Fall 2026": ["INST380"]}

    # Requirements are recalculated for the new major.
    tid_keys, progress = progress_keys(session)
    assert "tid.core" in tid_keys and "infosci.core" not in tid_keys
    assert progress["program"]["name"] == "Technology and Information Design"
    benchmark = next(u for u in progress["remaining_requirements"] + progress["completed_requirements"]
                     if u["key"] == "tid.benchmark")
    # Completed courses apply to the new major (SOCY105 is a TID benchmark).
    assert {"INST126", "INST201", "SOCY105", "STAT100"} <= {c["code"] for c in benchmark["applied_courses"]}
    # INST380 is a TID course: no restriction warning now, and it fills a requirement.
    inst380 = plan["terms"][0]["courses"][0]
    assert "Restricted to other programs." not in inst380["warnings"]
    assert "Do Good Now" in [s["name"] for s in inst380["satisfies"]]
    # Recommendations follow the new major.
    rec = client.post(url(session, "/recommendation")).json()
    assert "INST367" in [c["code"] for c in rec["additions"]]
    assert "INST335" not in [c["code"] for c in rec["additions"]]

    # The choice is saved.
    assert client.get(f"/api/sessions/{session['id']}").json()["program_slug"] == TID


def test_major_without_verified_requirements(session):
    add(session, "INST326", "Fall 2026")
    client.patch(f"/api/sessions/{session['id']}", json={"program_slug": UNVERIFIED})
    keys, progress = progress_keys(session)
    assert progress["program"]["requirements_status"] == "not_available"
    # Only university and Gen Ed requirements are evaluated: nothing made up for the major.
    assert keys and all(k.startswith("umd.") for k in keys)

    plan = client.get(url(session)).json()
    assert plan["requirements_verified"] is False
    assert plan["projected_graduation"] is None
    assert "doesn't have verified requirements" in plan["graduation_note"]
    assert term_codes(plan) == {"Fall 2026": ["INST326"]}  # the student can still plan

    response = client.post(url(session, "/recommendation"))
    assert response.status_code == 409
    assert "verified requirements" in response.json()["detail"]

    # Switching back restores the full picture with nothing lost.
    client.patch(f"/api/sessions/{session['id']}", json={"program_slug": INFOSCI})
    assert client.get(url(session)).json()["requirements_verified"] is True
    assert term_codes(client.get(url(session)).json()) == {"Fall 2026": ["INST326"]}
