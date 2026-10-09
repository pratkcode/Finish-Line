"""Prerequisite service tests.

Unit tests use small made-up graphs; the API tests at the end use the real
UMD catalog data (needs the seeded database).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.prerequisites import Checker, PrereqGraph, prerequisite_tree


def graph(prereqs: dict[str, list]) -> PrereqGraph:
    """prereqs: code -> list of groups; a group is a list of option codes, or
    (options, timing, min_grade)."""
    codes = set(prereqs)
    for groups in prereqs.values():
        for g in groups:
            codes.update(g[0] if isinstance(g, tuple) else g)
    courses = {c: {"code": c, "name": c, "credits_min": 3, "credits_max": 3,
                   "prerequisites_complete": True, "prerequisite_text": None} for c in codes}
    groups = {}
    for code, gs in prereqs.items():
        groups[code] = []
        for g in gs:
            options, timing, min_grade = g if isinstance(g, tuple) else (g, "before", None)
            groups[code].append({"options": options, "timing": timing, "min_grade": min_grade})
    return PrereqGraph(courses, groups)


def codes(refs):
    return [r["code"] for r in refs]


# The chain from the spec (made up; the real catalog differs):
# INST490 <- INST327 <- INST326 <- INST201
CHAIN = graph({
    "INST201": [],
    "INST326": [["INST201"]],
    "INST327": [["INST326"]],
    "INST490": [["INST327"]],
})


def test_no_prerequisites():
    result = Checker(CHAIN, {}).check("INST201")
    assert result["status"] == "available"
    assert result["groups"] == []
    assert result["complete_first"] == []


def test_one_prerequisite_met():
    result = Checker(CHAIN, {"INST326": "A"}).check("INST327")
    assert result["status"] == "available"
    assert result["groups"][0]["state"] == "met"
    assert result["groups"][0]["options"][0]["state"] == "completed"


def test_one_prerequisite_missing():
    result = Checker(CHAIN, {}).check("INST327")
    assert result["status"] == "blocked"
    assert result["groups"][0]["state"] == "missing"
    assert codes(result["complete_first"]) == ["INST201", "INST326"]


def test_multi_level_chain():
    checker = Checker(CHAIN, {"INST201": "A"})
    assert checker.check("INST326")["status"] == "available"
    assert checker.check("INST327")["status"] == "blocked"
    inst490 = checker.check("INST490")
    assert inst490["status"] == "blocked"
    # Deepest first, and INST201 (done) isn't listed.
    assert codes(inst490["complete_first"]) == ["INST326", "INST327"]
    # The direct prerequisite is shown as blocked, not just missing.
    assert inst490["groups"][0]["options"][0]["state"] == "blocked"


def test_multiple_prerequisites_all_required():
    g = graph({"C": [["A"], ["B"]]})
    assert Checker(g, {"A": "A"}).check("C")["status"] == "blocked"
    assert codes(Checker(g, {"A": "A"}).check("C")["complete_first"]) == ["B"]
    assert Checker(g, {"A": "A", "B": "B"}).check("C")["status"] == "available"


def test_alternatives_in_one_group():
    g = graph({"C": [["A", "B"]]})
    assert Checker(g, {"B": "A"}).check("C")["status"] == "available"
    assert Checker(g, {}).check("C")["status"] == "blocked"


def test_plan_picks_the_cheapest_alternative():
    # A needs X first; B has no prerequisites. Suggest B.
    g = graph({"C": [["A", "B"]], "A": [["X"]]})
    assert codes(Checker(g, {}).check("C")["complete_first"]) == ["B"]


def test_shared_prerequisite_listed_once():
    g = graph({"D": [["B"], ["C"]], "B": [["A"]], "C": [["A"]]})
    assert codes(Checker(g, {}).check("D")["complete_first"]) == ["A", "B", "C"]


def test_minimum_grade():
    g = graph({"B": [(["A"], "before", "C-")]})
    result = Checker(g, {"A": "D"}).check("B")
    assert result["status"] == "blocked"
    assert result["groups"][0]["options"][0]["state"] == "low_grade"
    assert codes(result["complete_first"]) == ["A"]  # retake it
    assert Checker(g, {"A": None}).check("B")["status"] == "available"  # no grade entered


def test_corequisite_and_concurrent_enrollment():
    g = graph({"LAB": [(["LEC"], "concurrent", None)],
               "ADV": [(["MID"], "before_or_concurrent", None)],
               "MID": [["BASE"]]})
    lab = Checker(g, {}).check("LAB")
    assert lab["status"] == "available_with_concurrent"
    assert codes(lab["take_with"]) == ["LEC"]
    # MID can't be taken this semester (needs BASE), so ADV is blocked.
    adv = Checker(g, {}).check("ADV")
    assert adv["status"] == "blocked"
    assert codes(adv["complete_first"]) == ["BASE"]
    assert codes(adv["take_with"]) == ["MID"]
    assert Checker(g, {"BASE": "A"}).check("ADV")["status"] == "available_with_concurrent"


def test_completed_course_and_retake():
    g = graph({"B": [["A"]]})
    assert Checker(g, {"B": "A", "A": "A"}).check("B")["status"] == "completed"
    assert Checker(g, {"B": "F", "A": "A"}).check("B", retake=True)["status"] == "available"


def test_cycles_do_not_loop_forever():
    g = graph({"A": [["B"]], "B": [["A"]]})
    assert Checker(g, {}).check("A")["status"] == "blocked"
    tree = prerequisite_tree(g, "A")
    assert tree["groups"][0]["options"][0]["groups"][0]["options"][0]["cycle"] is True


def test_prerequisite_tree_is_recursive():
    tree = prerequisite_tree(CHAIN, "INST490")
    level = tree
    seen = []
    while level["groups"]:
        level = level["groups"][0]["options"][0]
        seen.append(level["code"])
    assert seen == ["INST327", "INST326", "INST201"]


# --- API tests on the real catalog --------------------------------------------------

client = TestClient(app)


@pytest.fixture
def session():
    data = client.post("/api/sessions", json={"program_slug": "umd-information-science"}).json()
    yield data
    client.delete(f"/api/sessions/{data['id']}")


def add(session, *course_codes, grade="A"):
    for code in course_codes:
        client.post(f"/api/sessions/{session['id']}/courses", json={"code": code, "grade": grade})


def eligibility(session, code):
    response = client.get(f"/api/sessions/{session['id']}/eligibility/{code}")
    assert response.status_code == 200
    return response.json()


def test_api_prerequisite_tree():
    tree = client.get("/api/courses/INST346/prerequisite-tree").json()
    assert [codes(g["options"]) for g in tree["groups"]] == [
        ["INST201", "INST301"], ["INST326"], ["INST327"]]
    inst326 = tree["groups"][1]["options"][0]
    assert codes(inst326["groups"][0]["options"]) == ["GEOG276", "INST126"]
    assert client.get("/api/courses/FAKE999/prerequisite-tree").status_code == 404


def test_api_real_chain(session):
    # Real catalog: INST326 and INST327 need INST126 (or alternatives);
    # INST346 needs INST201/301, INST326 and INST327.
    add(session, "INST126", "INST201")
    assert eligibility(session, "INST326")["status"] == "available"
    inst346 = eligibility(session, "INST346")
    assert inst346["status"] == "blocked"
    assert codes(inst346["complete_first"]) == ["INST326", "INST327"]
    assert eligibility(session, "INST490")["status"] == "blocked"


def test_api_course_with_no_prerequisites(session):
    assert eligibility(session, "INST201")["status"] == "available"


def test_api_additional_conditions(session):
    # INST126's catalog prerequisite is math placement, which isn't a course.
    assert "Math placement" in eligibility(session, "INST126")["additional_conditions"]


def test_api_unknown_course(session):
    response = client.get(f"/api/sessions/{session['id']}/eligibility/FAKE999")
    assert response.status_code == 404


def test_api_remaining_course_analysis(session):
    add(session, "INST126", "INST201")
    add(session, "INST314", grade="D")  # too low for the major: a retake
    data = client.get(f"/api/sessions/{session['id']}/eligibility").json()
    available = {c["code"]: c for c in data["available"]}
    blocked = {c["code"]: c for c in data["blocked"]}

    assert "INST326" in available
    assert "INST346" in blocked
    assert codes(blocked["INST346"]["complete_first"]) == ["INST326", "INST327"]
    assert "infosci.core" in [r["key"] for r in available["INST326"]["satisfies"]]
    # Completed courses aren't listed; the D course is listed as a retake.
    assert "INST126" not in available and "INST126" not in blocked
    retake = available.get("INST314") or blocked.get("INST314")
    assert retake["retake"] is True

    missing = {m["code"]: m for m in data["missing_prerequisites"]}
    assert "INST346" in missing["INST326"]["unlocks"]
    assert missing["INST326"]["status"] == "available"
