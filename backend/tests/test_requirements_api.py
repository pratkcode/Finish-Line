"""Requirement API tests. These run against the seeded database (see README)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SLUG = "umd-information-science"


def find(nodes, key):
    for node in nodes:
        if node["key"] == key:
            return node
        found = find(node["children"], key)
        if found:
            return found
    return None


def codes(courses):
    return [c["code"] for c in courses]


def progress_for(courses):
    response = client.post(f"/api/programs/{SLUG}/progress", json={"courses": courses})
    assert response.status_code == 200
    return response.json()


def test_list_programs():
    programs = {p["slug"]: p for p in client.get("/api/programs").json()}
    assert programs[SLUG]["name"] == "Information Science"
    assert programs[SLUG]["university"] == "University of Maryland, College Park"
    assert programs[SLUG]["requirements_status"] == "verified"
    assert programs["umd-technology-info-design"]["requirements_status"] == "verified"
    # Every catalog major is listed; most don't have verified requirements yet.
    assert len(programs) > 100
    assert programs["umd-computer-science"]["requirements_status"] == "not_available"
    assert programs["umd-computer-science"]["catalog_url"].startswith("https://academiccatalog.umd.edu/")


def test_unknown_program():
    assert client.get("/api/programs/nope/requirements").status_code == 404
    assert client.post("/api/programs/nope/progress", json={"courses": []}).status_code == 404


def test_requirement_tree_structure():
    data = client.get(f"/api/programs/{SLUG}/requirements").json()
    roots = data["requirements"]
    assert [r["key"] for r in roots] == ["infosci.major", "umd.degree", "umd.gened"]
    assert [r["category"] for r in roots] == ["major", "university", "general_education"]
    assert all(r["progress"] is None for r in roots)


def test_core_courses_match_catalog():
    core = find(client.get(f"/api/programs/{SLUG}/requirements").json()["requirements"],
                "infosci.core")
    assert core["category"] == "major_core"
    assert core["rule"] == "all_courses"
    assert core["min_grade"] == "C-"
    assert codes(core["courses"]) == ["INST201", "INST311", "INST314", "INST326", "INST327",
                                      "INST335", "INST346", "INST352", "INST362", "INST490"]


def test_electives_are_upper_level_inst():
    tree = client.get(f"/api/programs/{SLUG}/requirements").json()["requirements"]
    electives = find(tree, "infosci.electives")
    assert electives["min_credits"] == 15
    assert electives["filters"] == [{"subject": "INST", "min_number": 300, "max_number": 499,
                                     "gen_ed": None}]
    eligible = codes(electives["eligible_courses"])
    assert "INST354" in eligible
    assert all(c.startswith("INST") and 300 <= int(c[4:]) <= 499 for c in eligible)


def test_gen_ed_requirement_uses_tags():
    tree = client.get(f"/api/programs/{SLUG}/requirements").json()["requirements"]
    big_question = find(tree, "umd.gened.big_question")
    assert big_question["filters"][0]["gen_ed"] == "SCIS"
    # Hundreds of Big Question courses across departments; the list is capped.
    assert big_question["eligible_count"] > 100  # 210 in the 2026-2027 data
    assert len(big_question["eligible_courses"]) == 50
    listed = codes(big_question["eligible_courses"])
    assert len({c[:4] for c in listed}) > 5
    for code in listed[:5] + ["INST104", "INST204"]:
        assert "SCIS" in client.get(f"/api/courses/{code}").json()["gen_ed"]


def test_progress_checklist():
    data = progress_for([
        {"code": "INST201", "grade": "A"},
        {"code": "inst 311", "grade": "B"},     # codes are normalized
        {"code": "INST314", "grade": "D"},      # below C-: doesn't count for the major
        {"code": "INST354", "grade": "A-"},
        {"code": "ZZZZ999", "grade": "A"},      # not a UMD course
    ])
    tree = data["requirements"]
    core = find(tree, "infosci.core")["progress"]
    assert core["status"] == "in_progress"
    assert codes(core["applied_courses"]) == ["INST201", "INST311"]
    assert core["courses_remaining"] == 8

    electives = find(tree, "infosci.electives")["progress"]
    assert codes(electives["applied_courses"]) == ["INST354"]
    assert electives["credits_remaining"] == 12

    # A D still earns credit toward the degree total.
    assert "INST314" in codes(find(tree, "umd.degree.total_credits")["progress"]["applied_courses"])
    assert data["unrecognized_courses"] == ["ZZZZ999"]


def test_core_course_is_not_also_an_elective():
    tree = progress_for([{"code": "INST326", "grade": "A"}])["requirements"]
    assert codes(find(tree, "infosci.core")["progress"]["applied_courses"]) == ["INST326"]
    assert find(tree, "infosci.electives")["progress"]["applied_courses"] == []


def test_gen_ed_course_can_also_count_for_major():
    tree = progress_for([{"code": "INST201", "grade": "A"}])["requirements"]
    assert codes(find(tree, "infosci.core")["progress"]["applied_courses"]) == ["INST201"]
    assert codes(find(tree, "umd.gened.dshs")["progress"]["applied_courses"]) == ["INST201"]


def test_completed_major_core():
    core_codes = ["INST201", "INST311", "INST314", "INST326", "INST327",
                  "INST335", "INST346", "INST352", "INST362", "INST490"]
    tree = progress_for([{"code": c, "grade": "B"} for c in core_codes])["requirements"]
    assert find(tree, "infosci.core")["progress"]["status"] == "complete"
    assert find(tree, "infosci.major")["progress"]["status"] == "in_progress"


def test_untracked_requirements():
    tree = progress_for([])["requirements"]
    assert find(tree, "umd.degree.gpa")["progress"]["status"] == "not_tracked"
    assert find(tree, "infosci.cognate.data_science")["progress"]["status"] == "not_tracked"


def test_invalid_grade_rejected():
    response = client.post(f"/api/programs/{SLUG}/progress",
                           json={"courses": [{"code": "INST201", "grade": "Z"}]})
    assert response.status_code == 422
