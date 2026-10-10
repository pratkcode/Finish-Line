"""Dashboard summary tests (needs the seeded database)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_summary_for_a_student():
    session = client.post("/api/sessions", json={
        "program_slug": "umd-information-science", "reported_credits": 61,
        "current_term": "Spring 2026", "max_credits_per_term": 15}).json()
    try:
        for code in ["MATH115", "PSYC100", "STAT100", "INST126", "INST201"]:
            client.post(f"/api/sessions/{session['id']}/courses", json={"code": code, "grade": "B"})
        empty = client.get(f"/api/sessions/{session['id']}/summary").json()
        client.post(f"/api/sessions/{session['id']}/plan/courses",
                    json={"code": "INST326", "term": "Fall 2026"})
        client.post(f"/api/sessions/{session['id']}/plan/courses",
                    json={"code": "INST311", "term": "Spring 2027"})
        summary = client.get(f"/api/sessions/{session['id']}/summary").json()
        progress = client.get(f"/api/sessions/{session['id']}/progress").json()
        plan = client.get(f"/api/sessions/{session['id']}/plan").json()
    finally:
        client.delete(f"/api/sessions/{session['id']}")

    assert summary["program"]["name"] == "Information Science"
    assert summary["completed_courses"] == 5
    # The reported total (61) isn't counted until the credits are recorded.
    assert summary["credits"] == {"earned": 15, "from_courses": 15, "in_progress": 0,
                                  "unverified": 46, "required": 120, "remaining": 105}
    # The summary agrees with the detailed endpoints.
    complete = len(progress["completed_requirements"])
    total = complete + len(progress["remaining_requirements"])
    assert summary["requirements"]["complete"] == complete
    assert summary["requirements"]["percent"] == round(100 * complete / total)
    # Nothing is planned until the student adds courses.
    assert empty["next_term"] is None
    assert empty["graduation"]["planned_courses"] == 0
    assert empty["graduation"]["projected"] is None
    # The summary reflects the saved plan.
    assert summary["graduation"]["projected"] == plan["projected_graduation"]
    assert summary["graduation"]["semesters"] == len(plan["terms"]) == 2
    assert summary["graduation"]["planned_courses"] == 2
    assert summary["next_term"] == {"term": "Fall 2026", "credits": 3, "courses": ["INST326"]}
    assert summary["eligibility"]["available"] > 0


def test_summary_unknown_session():
    response = client.get("/api/sessions/00000000-0000-0000-0000-000000000000/summary")
    assert response.status_code == 404
