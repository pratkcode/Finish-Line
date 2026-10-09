"""Dashboard summary tests (needs the seeded database)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_summary_for_a_student():
    session = client.post("/api/sessions", json={
        "program_slug": "umd-information-science", "reported_credits": 61,
        "current_term": "Fall 2026", "max_credits_per_term": 15}).json()
    try:
        for code in ["MATH115", "PSYC100", "STAT100", "INST126", "INST201"]:
            client.post(f"/api/sessions/{session['id']}/courses", json={"code": code, "grade": "B"})
        summary = client.get(f"/api/sessions/{session['id']}/summary").json()
        progress = client.get(f"/api/sessions/{session['id']}/progress").json()
        plan = client.get(f"/api/sessions/{session['id']}/plan").json()
    finally:
        client.delete(f"/api/sessions/{session['id']}")

    assert summary["program"]["name"] == "Information Science"
    assert summary["completed_courses"] == 5
    assert summary["credits"] == {"earned": 61, "from_courses": 15, "unverified": 46,
                                  "required": 120, "remaining": 59}
    # The summary agrees with the detailed endpoints.
    complete = len(progress["completed_requirements"])
    total = complete + len(progress["remaining_requirements"])
    assert summary["requirements"]["complete"] == complete
    assert summary["requirements"]["percent"] == round(100 * complete / total)
    assert summary["graduation"]["projected"] == plan["projected_graduation"]
    assert summary["graduation"]["semesters"] == len(plan["terms"])
    assert summary["next_term"]["term"] == "Fall 2026"
    assert summary["next_term"]["credits"] <= 15
    assert summary["eligibility"]["available"] > 0


def test_summary_unknown_session():
    response = client.get("/api/sessions/00000000-0000-0000-0000-000000000000/summary")
    assert response.status_code == 404
