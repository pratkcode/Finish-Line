"""Planning session API tests. These run against the seeded database (see README)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SLUG = "umd-information-science"


@pytest.fixture
def session():
    created = client.post("/api/sessions", json={
        "program_slug": SLUG, "reported_credits": 61,
        "current_term": "Fall 2026", "max_credits_per_term": 15,
    })
    assert created.status_code == 201
    data = created.json()
    yield data
    client.delete(f"/api/sessions/{data['id']}")


def url(session, path=""):
    return f"/api/sessions/{session['id']}{path}"


def test_create_session(session):
    assert session["program_slug"] == SLUG
    assert session["program_name"] == "Information Science"
    assert session["university"] == "University of Maryland, College Park"
    assert session["current_term"] == "Fall 2026"
    assert session["max_credits_per_term"] == 15
    assert session["courses"] == []
    assert session["credits"] == {"completed": 0, "reported": 61, "unmatched": 61,
                                  "reported_too_low": False}


def test_add_and_list_course(session):
    response = client.post(url(session, "/courses"), json={"code": "inst 326"})
    assert response.status_code == 201
    course = response.json()["courses"][0]
    assert course == {"code": "INST326",
                      "name": "Object-Oriented Programming for Information Science",
                      "credits": 3, "credits_min": 3, "credits_max": 3, "grade": None}

    listed = client.get(url(session, "/courses")).json()
    assert [c["code"] for c in listed] == ["INST326"]


def test_data_persists_across_requests(session):
    client.post(url(session, "/courses"), json={"code": "INST326", "grade": "A"})
    client.post(url(session, "/courses"), json={"code": "INST201"})
    client.patch(url(session), json={"max_credits_per_term": 12})

    reloaded = client.get(url(session)).json()
    assert [c["code"] for c in reloaded["courses"]] == ["INST201", "INST326"]
    assert reloaded["max_credits_per_term"] == 12
    assert reloaded["credits"]["completed"] == 6


def test_credits_are_calculated_from_courses(session):
    for code in ["INST126", "INST201", "STAT100"]:
        client.post(url(session, "/courses"), json={"code": code})
    credits = client.get(url(session)).json()["credits"]
    assert credits["completed"] == 9
    assert credits["reported"] == 61
    assert credits["unmatched"] == 52


def test_reported_total_lower_than_courses_is_flagged(session):
    client.patch(url(session), json={"reported_credits": 3})
    for code in ["INST126", "INST201"]:
        client.post(url(session, "/courses"), json={"code": code})
    credits = client.get(url(session)).json()["credits"]
    assert credits["completed"] == 6  # the course list wins
    assert credits["reported_too_low"] is True
    assert credits["unmatched"] == 0


def test_remove_course(session):
    client.post(url(session, "/courses"), json={"code": "INST326"})
    client.post(url(session, "/courses"), json={"code": "INST327"})
    response = client.delete(url(session, "/courses/INST326"))
    assert response.status_code == 200
    assert [c["code"] for c in response.json()["courses"]] == ["INST327"]
    assert response.json()["credits"]["completed"] == 3
    assert client.delete(url(session, "/courses/INST326")).status_code == 404


def test_duplicate_and_unknown_courses_rejected(session):
    client.post(url(session, "/courses"), json={"code": "INST326"})
    assert client.post(url(session, "/courses"), json={"code": "INST326"}).status_code == 409
    assert client.post(url(session, "/courses"), json={"code": "FAKE999"}).status_code == 404


def test_variable_credit_course(session):
    # INST408 is 1-6 credits.
    assert client.post(url(session, "/courses"),
                       json={"code": "INST408", "credits": 9}).status_code == 422
    added = client.post(url(session, "/courses"), json={"code": "INST408", "credits": 3}).json()
    assert added["courses"][0]["credits"] == 3
    updated = client.patch(url(session, "/courses/INST408"), json={"credits": 2}).json()
    assert updated["credits"]["completed"] == 2


def test_update_grade(session):
    client.post(url(session, "/courses"), json={"code": "INST326"})
    updated = client.patch(url(session, "/courses/INST326"), json={"grade": "B+"}).json()
    assert updated["courses"][0]["grade"] == "B+"
    assert client.patch(url(session, "/courses/INST326"),
                        json={"grade": "Q"}).status_code == 422


def test_update_profile(session):
    updated = client.patch(url(session), json={"current_term": "Spring 2027",
                                               "reported_credits": None})
    assert updated.status_code == 200
    assert updated.json()["current_term"] == "Spring 2027"
    assert updated.json()["credits"]["reported"] is None
    assert client.patch(url(session), json={"current_term": "Autumn 2026"}).status_code == 422
    assert client.patch(url(session), json={"max_credits_per_term": 0}).status_code == 422
    assert client.patch(url(session), json={"program_slug": "nope"}).status_code == 404


def test_missing_session():
    missing = "/api/sessions/00000000-0000-0000-0000-000000000000"
    assert client.get(missing).status_code == 404
    assert client.post(f"{missing}/courses", json={"code": "INST326"}).status_code == 404
    assert client.get("/api/sessions/not-a-uuid").status_code == 422


def test_delete_session(session):
    client.post(url(session, "/courses"), json={"code": "INST326"})
    assert client.delete(url(session)).status_code == 204
    assert client.get(url(session)).status_code == 404
