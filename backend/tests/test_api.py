"""API tests. These run against the seeded database (see README)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_list_courses():
    response = client.get("/api/courses")
    courses = response.json()
    codes = [c["code"] for c in courses]
    # The whole catalog across departments, returned a page at a time.
    assert int(response.headers["X-Total-Count"]) > 5000
    assert len(codes) == 200
    assert codes == sorted(codes)
    assert set(courses[0]) == {"code", "name", "credits_min", "credits_max"}
    assert "INST326" in [c["code"] for c in client.get("/api/courses", params={"search": "INST326"}).json()]


def test_search_by_code():
    codes = [c["code"] for c in client.get("/api/courses", params={"search": "inst 32"}).json()]
    assert "INST326" in codes
    assert "INST327" in codes
    assert all(code.startswith("INST32") for code in codes)


def test_search_by_name():
    courses = client.get("/api/courses", params={"search": "database"}).json()
    assert "INST327" in [c["code"] for c in courses]


def test_search_no_results():
    assert client.get("/api/courses", params={"search": "zzzz"}).json() == []


def test_get_course():
    course = client.get("/api/courses/inst326").json()
    assert course["code"] == "INST326"
    assert course["name"] == "Object-Oriented Programming for Information Science"
    assert course["credits_min"] == course["credits_max"] == 3
    assert course["description"]
    assert course["prerequisites"]["course_code"] == "INST326"


def test_get_course_not_found():
    response = client.get("/api/courses/FAKE999")
    assert response.status_code == 404
    assert client.get("/api/courses/FAKE999/prerequisites").status_code == 404


def option_codes(prereqs):
    return [sorted(o["code"] for o in g["options"]) for g in prereqs["groups"]]


def test_prerequisites_single_group_with_alternatives():
    prereqs = client.get("/api/courses/INST326/prerequisites").json()
    assert option_codes(prereqs) == [["GEOG276", "INST126"]]
    assert prereqs["groups"][0]["min_grade"] == "C-"
    assert prereqs["complete"] is True


def test_prerequisites_multiple_groups():
    prereqs = client.get("/api/courses/INST346/prerequisites").json()
    assert option_codes(prereqs) == [["INST201", "INST301"], ["INST326"], ["INST327"]]


def test_prerequisites_concurrent_timing():
    prereqs = client.get("/api/courses/INST127/prerequisites").json()
    assert prereqs["groups"][0]["timing"] == "concurrent"
    timings = [g["timing"] for g in client.get("/api/courses/INST454/prerequisites").json()["groups"]]
    assert timings.count("before_or_concurrent") == 1


def test_prerequisites_incomplete_keeps_official_text():
    prereqs = client.get("/api/courses/INST126/prerequisites").json()
    assert prereqs["groups"] == []
    assert prereqs["complete"] is False
    assert "Math placement" in prereqs["prerequisite_text"]


def test_course_without_prerequisites():
    prereqs = client.get("/api/courses/INST201/prerequisites").json()
    assert prereqs["groups"] == []
    assert prereqs["complete"] is True
    assert prereqs["prerequisite_text"] is None


def test_variable_credit_course():
    course = client.get("/api/courses/INST408").json()
    assert course["credits_min"] < course["credits_max"]


def test_search_treats_wildcards_literally():
    assert client.get("/api/courses", params={"search": "%"}).json() == []
    assert client.get("/api/courses", params={"search": "_"}).json() == []
    assert client.get("/api/courses", params={"search": "x" * 101}).status_code == 422


def test_course_detail_includes_catalog_details():
    course = client.get("/api/courses/INST104").json()
    assert course["gen_ed"] == ["DSHU", "SCIS"]
    assert course["gen_ed_text"] == "DSHU, SCIS"
    inst490 = client.get("/api/courses/INST490").json()
    assert "minimum of 90 credits" in inst490["restriction_text"]


def test_dependents_are_reverse_prerequisites():
    dependents = {d["code"]: d for d in client.get("/api/courses/INST326/dependents").json()}
    assert {"INST346", "INST362", "INST490"} <= set(dependents)
    # INST447 accepts BSOS326 or INST326 for the same requirement.
    assert dependents["INST447"]["alternatives"] == ["BSOS326"]
    assert client.get("/api/courses/INST490/dependents").json() == []
    assert client.get("/api/courses/FAKE999/dependents").status_code == 404


def test_database_outage_returns_503(monkeypatch):
    import psycopg

    def unavailable():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr("app.courses.get_connection", unavailable)
    response = client.get("/api/courses")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_total_count_header_is_readable_cross_origin():
    response = client.get("/api/courses", headers={"Origin": "http://localhost:3000"})
    assert "X-Total-Count" in response.headers["access-control-expose-headers"]
