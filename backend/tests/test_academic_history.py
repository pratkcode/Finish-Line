"""Academic history, transfer credit, verified fulfillments and flexible plan
timelines (needs the migrated, seeded database).

Scenarios:
  A. a first-year student with no credits
  B. a transfer student with 60 verified credits and Gen Ed verified complete
  C. a transfer student with 45 credits and some Gen Ed met
  D. coursework at several institutions
  E. in-progress courses aren't completed courses
  F. transfer credit that doesn't map to a UMD course
  G. a plan starting in Fall 2026, Spring 2027 or Summer 2027
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
INFOSCI = "umd-information-science"


@pytest.fixture
def make_session():
    created = []

    def make(**fields):
        body = {"program_slug": INFOSCI, "current_term": "Fall 2026",
                "max_credits_per_term": 15, **fields}
        response = client.post("/api/sessions", json=body)
        assert response.status_code == 201, response.text
        created.append(response.json()["id"])
        return response.json()["id"]

    yield make
    for session_id in created:
        client.delete(f"/api/sessions/{session_id}")


def api(session_id, path=""):
    return f"/api/sessions/{session_id}{path}"


def add_term(session_id, term, institution=None, at_umd=True):
    response = client.post(api(session_id, "/history/terms"),
                           json={"term": term, "institution": institution, "at_umd": at_umd})
    assert response.status_code == 201, response.text
    return next(t["id"] for t in response.json()["terms"]
                if t["term"] == term and t["at_umd"] == at_umd)


def add_course(session_id, code, grade="B", **extra):
    response = client.post(api(session_id, "/courses"), json={"code": code, "grade": grade, **extra})
    assert response.status_code == 201, response.text


def add_transfer(session_id, **fields):
    response = client.post(api(session_id, "/transfer-credits"),
                           json={"institution": "Montgomery College", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def add_fulfillment(session_id, key, verification, method="transfer_credit"):
    response = client.post(api(session_id, "/fulfillments"), json={
        "requirement_key": key, "method": method, "verification": verification})
    assert response.status_code == 201, response.text
    return response.json()


def progress(session_id):
    response = client.get(api(session_id, "/progress"))
    assert response.status_code == 200, response.text
    return response.json()


def find_unit(data, key):
    units = data["completed_requirements"] + data["remaining_requirements"]
    return next(u for u in units if u["key"] == key)


def is_complete(data, key):
    return key in [u["key"] for u in data["completed_requirements"]]


def recommend(session_id):
    response = client.post(api(session_id, "/plan/recommendation"))
    assert response.status_code == 200, response.text
    return response.json()


def rec_terms(rec):
    return [c["term"] for c in rec["additions"] + rec["slots"]]


GENED_UNITS = ["umd.gened.fsaw", "umd.gened.fspw", "umd.gened.fsoc", "umd.gened.fsma",
               "umd.gened.fsar", "umd.gened.dshs", "umd.gened.dshu", "umd.gened.dssp"]


# --- A. First-year student ---------------------------------------------------------------

def test_a_first_year_student_with_no_credits(make_session):
    session_id = make_session()
    data = progress(session_id)
    assert data["credits"]["applicable"] == 0
    assert data["credits"]["remaining"] == 120
    assert data["pending"] == []

    plan = client.get(api(session_id, "/plan")).json()
    assert plan["history"] == []
    assert plan["current_term"] == "Fall 2026"
    assert plan["plan_start_term"] == "Spring 2027"  # the semester after the current one
    assert plan["planning_terms"][0] == "Spring 2027"

    rec = recommend(session_id)
    assert rec["start_term"] == "Spring 2027"
    assert min(rec_terms(rec), key=plan_order) == "Spring 2027"
    # Gen Ed is still needed, and every recommendation says why it's there.
    assert any(s["category"] == "general_education"
               for c in rec["additions"] + rec["slots"] for s in c["satisfies"])
    assert all(c["reasons"] for c in rec["additions"] + rec["slots"])


# --- B. Transfer: 60 credits, Gen Ed verified complete --------------------------------------

def test_b_transfer_with_verified_gened(make_session):
    session_id = make_session()
    add_transfer(session_id, kind="credits", title="Associate of Arts", credits=60,
                 verification="umd_verified")
    add_fulfillment(session_id, "umd.gened", "umd_verified", method="associate_degree")

    data = progress(session_id)
    assert data["credits"]["applicable"] == 60
    assert data["credits"]["credit_block"] == 60
    assert data["credits"]["remaining"] == 60
    for key in GENED_UNITS:
        assert is_complete(data, key), key
        assert find_unit(data, key)["fulfilled"] is True
    # The block of credit doesn't fill any major requirement.
    assert not is_complete(data, "infosci.core")

    rec = recommend(session_id)
    categories = {s["category"] for c in rec["additions"] + rec["slots"] for s in c["satisfies"]}
    assert "general_education" not in categories
    assert any(c["code"] == "INST326" for c in rec["additions"])
    assert any("without a UMD equivalent" in a for a in rec["assumptions"])


def test_b_gened_counted_once_and_unverified_claims_dont_count(make_session):
    session_id = make_session()
    add_fulfillment(session_id, "umd.gened.fsaw", "student_reported")
    data = progress(session_id)
    assert not is_complete(data, "umd.gened.fsaw")
    assert any(p["kind"] == "fulfillment" for p in data["pending"])

    # The same requirement can't be recorded twice.
    duplicate = client.post(api(session_id, "/fulfillments"), json={
        "requirement_key": "umd.gened.fsaw", "method": "waiver", "verification": "umd_verified"})
    assert duplicate.status_code == 409
    # Requirements must be real.
    unknown = client.post(api(session_id, "/fulfillments"), json={
        "requirement_key": "umd.gened.made_up", "method": "waiver"})
    assert unknown.status_code == 404

    # Approving it (an approved exception) makes it count.
    history = client.get(api(session_id, "/history")).json()
    [fulfillment] = history["fulfillments"]
    assert fulfillment["counted"] is False
    response = client.patch(api(session_id, f"/fulfillments/{fulfillment['id']}"),
                            json={"verification": "approved_exception", "method": "waiver"})
    assert response.status_code == 200, response.text
    assert is_complete(progress(session_id), "umd.gened.fsaw")


# --- C. Transfer: 45 credits, some Gen Ed met ---------------------------------------------

def test_c_transfer_with_some_gened(make_session):
    session_id = make_session()
    add_transfer(session_id, external_code="ENG 101", title="English Composition", credits=3,
                 equivalent_code="ENGL101", verification="umd_verified")
    add_transfer(session_id, external_code="MA 181", title="Calculus I", credits=4,
                 equivalent_code="MATH115", verification="umd_verified")
    add_transfer(session_id, external_code="PSYC 102", title="General Psychology", credits=3,
                 equivalent_code="PSYC100", verification="student_reported")
    add_transfer(session_id, kind="credits", title="Electives", credits=35,
                 verification="umd_verified")

    data = progress(session_id)
    assert data["credits"]["earned"] == 45
    assert data["credits"]["applicable"] == 42  # PSYC 102 isn't verified
    assert data["credits"]["unverified"] == 3
    assert is_complete(data, "umd.gened.fsaw")  # through the verified ENGL101 equivalent
    assert [p["credits"] for p in data["pending"] if p["kind"] == "transfer"] == [3]
    assert not is_complete(data, "infosci.core")

    history = client.get(api(session_id, "/history")).json()
    assert history["summary"]["applicable_credits"] == 42
    counted = {t["external_code"]: t["counted"] for t in history["unassigned_transfers"]}
    assert counted == {"ENG 101": True, "MA 181": True, "PSYC 102": False, None: True}

    # A transfer equivalent is a completed course: it can't be planned again.
    response = client.post(api(session_id, "/plan/courses"),
                           json={"code": "ENGL101", "term": "Spring 2027"})
    assert response.status_code == 409
    # The unverified one can be planned, with a note about the pending credit.
    plan = client.post(api(session_id, "/plan/courses"),
                       json={"code": "PSYC100", "term": "Spring 2027"}).json()
    [course] = plan["terms"][0]["courses"]
    assert any("reported transfer credit" in n for n in course["notes"])


def test_c_transfer_duplicate_of_umd_course_counts_once(make_session):
    session_id = make_session()
    add_course(session_id, "ENGL101", "A")
    add_transfer(session_id, external_code="ENG 101", credits=3, equivalent_code="ENGL101",
                 verification="umd_verified")
    data = progress(session_id)
    assert data["credits"]["applicable"] == 3
    assert any("Duplicates ENGL101" in p["reason"] for p in data["pending"])


# --- D. Several institutions ------------------------------------------------------------

def test_d_courses_at_multiple_institutions(make_session):
    session_id = make_session()
    montgomery = add_term(session_id, "Fall 2024", "Montgomery College", at_umd=False)
    nova = add_term(session_id, "Summer 2025", "Northern Virginia Community College",
                    at_umd=False)
    umd = add_term(session_id, "Spring 2025")
    add_transfer(session_id, academic_term_id=montgomery, external_code="ENG 101", credits=3,
                 equivalent_code="ENGL101", verification="umd_verified")
    add_transfer(session_id, academic_term_id=nova, external_code="STA 240", credits=3,
                 equivalent_code="STAT100", verification="umd_verified")
    add_course(session_id, "INST126", "A", academic_term_id=umd)

    # A UMD course can't go in another school's semester.
    response = client.post(api(session_id, "/courses"),
                           json={"code": "INST201", "academic_term_id": montgomery})
    assert response.status_code == 422

    history = client.get(api(session_id, "/history")).json()
    assert [(t["term"], t["institution"]) for t in history["terms"]] == [
        ("Fall 2024", "Montgomery College"),
        ("Spring 2025", "University of Maryland, College Park"),
        ("Summer 2025", "Northern Virginia Community College"),
    ]
    assert all(t["period"] == "past" for t in history["terms"])
    assert history["terms"][0]["transfers"][0]["institution"] == "Montgomery College"
    assert [c["code"] for c in history["terms"][1]["courses"]] == ["INST126"]
    assert history["summary"]["applicable_credits"] == 9

    # Past semesters appear on the plan as history.
    plan = client.get(api(session_id, "/plan")).json()
    assert [t["term"] for t in plan["history"]] == ["Fall 2024", "Spring 2025", "Summer 2025"]

    # Removing a semester removes what was recorded in it.
    assert client.delete(api(session_id, f"/history/terms/{montgomery}")).status_code == 200
    assert progress(session_id)["credits"]["applicable"] == 6

    # Editing a semester.
    response = client.patch(api(session_id, f"/history/terms/{nova}"), json={"term": "Summer 2024"})
    assert response.status_code == 200
    assert response.json()["terms"][0]["term"] == "Summer 2024"


# --- E. In-progress courses ------------------------------------------------------------

def test_e_in_progress_courses_are_not_completed(make_session):
    session_id = make_session()
    current = add_term(session_id, "Fall 2026")
    for code in ["MATH115", "PSYC100", "STAT100"]:
        add_course(session_id, code)
    add_course(session_id, "INST126", None, status="in_progress", academic_term_id=current)

    # An in-progress course can't have a grade.
    response = client.post(api(session_id, "/courses"),
                           json={"code": "INST201", "grade": "A", "status": "in_progress"})
    assert response.status_code == 422

    data = progress(session_id)
    assert data["credits"]["in_progress"] == 3
    assert data["credits"]["applicable"] == 9
    benchmark = find_unit(data, "infosci.benchmark")
    assert not is_complete(data, "infosci.benchmark")
    assert "INST126" in benchmark["in_progress_courses"]
    # It isn't suggested again.
    assert "INST126" not in [c["code"] for c in benchmark["candidate_courses"]]

    # Eligibility doesn't treat it as done yet.
    assert client.get(api(session_id, "/eligibility/INST326")).json()["status"] == "blocked"

    plan = client.get(api(session_id, "/plan")).json()
    assert plan["history"][0]["period"] == "current"
    assert plan["credits"]["in_progress"] == 3
    assert plan["credits"]["total"] == 12
    # It can't be planned again, but the plan treats it as done by next semester.
    assert client.post(api(session_id, "/plan/courses"),
                       json={"code": "INST126", "term": "Spring 2027"}).status_code == 409
    plan = client.post(api(session_id, "/plan/courses"),
                       json={"code": "INST326", "term": "Spring 2027"}).json()
    assert plan["warnings"] == []
    assert any("INST126" in a for a in recommend(session_id)["assumptions"])

    # Finishing it: mark completed with a grade.
    response = client.patch(api(session_id, "/courses/INST126"),
                            json={"status": "completed", "grade": "A"})
    assert response.status_code == 200, response.text
    assert is_complete(progress(session_id), "infosci.benchmark")


# --- F. Credit without a UMD equivalent ---------------------------------------------------

def test_f_unmapped_transfer_credits(make_session):
    session_id = make_session()
    add_transfer(session_id, kind="credits", title="Lower-level electives", credits=12,
                 verification="umd_verified")
    add_transfer(session_id, external_code="ART 110", title="Drawing I", credits=3,
                 verification="umd_verified")  # no UMD equivalent
    add_transfer(session_id, kind="credits", title="Exam credit", credits=6)  # not verified

    data = progress(session_id)
    assert data["credits"]["credit_block"] == 15
    assert data["credits"]["applicable"] == 15
    assert data["credits"]["unverified"] == 6
    total = find_unit(data, "umd.degree.total_credits")
    assert total["credits_remaining"] == 105
    # They don't fill any specific requirement.
    assert not any(is_complete(data, key) for key in GENED_UNITS)

    # Only a course can name an equivalent.
    response = client.post(api(session_id, "/transfer-credits"), json={
        "institution": "X", "kind": "credits", "credits": 3, "equivalent_code": "ENGL101"})
    assert response.status_code == 422
    # An equivalent must be a real UMD course.
    response = client.post(api(session_id, "/transfer-credits"), json={
        "institution": "X", "external_code": "X 1", "credits": 3, "equivalent_code": "ZZZZ999"})
    assert response.status_code == 404


# --- G. Plan start --------------------------------------------------------------------

@pytest.mark.parametrize("start, current, settings", [
    ("Fall 2026", "Spring 2026", {}),
    ("Spring 2027", "Fall 2026", {}),
    ("Summer 2027", "Fall 2026", {"include_summer": True, "max_summer_credits": 6}),
])
def test_g_plan_start_term(make_session, start, current, settings):
    session_id = make_session(current_term=current, plan_start_term=start, **settings)
    plan = client.get(api(session_id, "/plan")).json()
    assert plan["plan_start_term"] == start
    assert plan["planning_terms"][0] == start

    rec = recommend(session_id)
    assert rec["start_term"] == start
    first = min(rec_terms(rec), key=lambda t: plan_order(t))
    assert first == start
    if settings:
        summer = sum(c["credits"] for c in rec["additions"] + rec["slots"] if c["term"] == start)
        assert 0 < summer <= 6
    # Accepting it saves the courses from the chosen start on.
    accepted = client.post(api(session_id, "/plan/recommendation/accept"), json={
        "courses": [{"code": c["code"], "term": c["term"]} for c in rec["additions"]]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["terms"][0]["term"] == start

    # Nothing can be planned before the start.
    before = {"Fall 2026": "Spring 2026", "Spring 2027": "Fall 2026",
              "Summer 2027": "Spring 2027"}[start]
    response = client.post(api(session_id, "/plan/courses"),
                           json={"code": "INST314", "term": before})
    assert response.status_code in (409, 422)


def plan_order(term):
    season, year = term.split()
    return int(year) * 4 + ["Winter", "Spring", "Summer", "Fall"].index(season)


def test_plan_start_can_change_and_cannot_precede_current_term(make_session):
    session_id = make_session()
    assert client.patch(api(session_id), json={"plan_start_term": "Spring 2026"}).status_code == 422
    response = client.patch(api(session_id), json={"plan_start_term": "Fall 2027"})
    assert response.status_code == 200
    plan = client.get(api(session_id, "/plan")).json()
    assert plan["planning_terms"][0] == "Fall 2027"
    assert client.post(api(session_id, "/plan/courses"),
                       json={"code": "INST326", "term": "Spring 2027"}).status_code == 422


def test_summer_courses_warn_when_not_offered_in_summer(make_session):
    session_id = make_session(include_summer=True)
    # INST354 had Fall and Spring sections, but none in Summer, in the terms checked.
    plan = client.post(api(session_id, "/plan/courses"),
                       json={"code": "INST354", "term": "Summer 2027"}).json()
    [course] = plan["terms"][0]["courses"]
    assert any("No Summer sections" in w for w in course["warnings"])
    assert "Summer 2027" in plan["planning_terms"]


def test_target_graduation_is_checked(make_session):
    session_id = make_session(target_graduation_term="Spring 2027")
    rec = recommend(session_id)
    assert rec["target"]["term"] == "Spring 2027"
    assert rec["target"]["meets"] is False  # a whole degree can't fit in one semester
    plan = client.get(api(session_id, "/plan")).json()
    assert plan["target"]["meets"] is None  # nothing planned yet
    assert "Spring 2027" in plan["planning_terms"]
