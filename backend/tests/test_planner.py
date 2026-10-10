"""Semester planner tests.

Unit tests build small made-up degrees; the API test at the end checks a plan
for the real UMD Information Science data (needs the seeded database).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.planner import Calendar, Rules, build_plan, next_term
from app.prerequisites import PrereqGraph


# --- Helpers -----------------------------------------------------------------------

def make_graph(credits: dict[str, int], prereqs: dict[str, list] = None) -> PrereqGraph:
    """prereqs: code -> groups; a group is [options] or (options, timing)."""
    courses = {c: {"code": c, "name": f"Course {c}", "credits_min": n, "credits_max": n,
                   "prerequisites_complete": True, "prerequisite_text": None}
               for c, n in credits.items()}
    groups = {}
    for code, gs in (prereqs or {}).items():
        groups[code] = [
            {"options": list(g[0]), "timing": g[1], "min_grade": None} if isinstance(g, tuple)
            else {"options": list(g), "timing": "before", "min_grade": None}
            for g in gs
        ]
    return PrereqGraph(courses, groups)


def req(key, rule, eligible=(), children=(), graph=None, **fields):
    node = {"key": key, "name": key, "rule": rule, "category": "major",
            "eligible": list(eligible), "children": list(children),
            "min_courses": None, "min_credits": None, "min_grade": None,
            "allocation_group": "major", "optional": False, "any_course": False, **fields}
    node["eligible_courses"] = [
        {"code": c, "name": c, "credits_min": graph.courses[c]["credits_min"] if graph else 3,
         "credits_max": graph.courses[c]["credits_max"] if graph else 3}
        for c in node["eligible"]
    ]
    return node


def rules(restrictions=None, exclusions=()):
    return Rules("Test Major", restrictions or {}, list(exclusions))


def plan(tree, graph, completed=None, max_credits=9, start="Fall 2026", rules_=None,
         unverified=0):
    completed = {c: {"grade": g, "credits": graph.courses[c]["credits_min"]}
                 for c, g in (completed or {}).items()}
    return build_plan(tree, graph, rules_ or rules(), completed, unverified, start, max_credits)


def term_index(result) -> dict[str, int]:
    return {c["code"] or c["name"]: i for i, t in enumerate(result["terms"]) for c in t["courses"]}


def assert_valid(result, graph, max_credits):
    """Every plan must respect prerequisites and the credit limit."""
    where = term_index(result)
    for t in result["terms"]:
        assert t["credits"] <= max_credits
        assert t["credits"] == sum(c["credits"] for c in t["courses"])
    for code, index in where.items():
        for group in graph.groups.get(code, []):
            planned = [o for o in group["options"] if o in where]
            if not planned:
                continue  # met by a completed course
            earliest = min(where[o] for o in planned)
            if group["timing"] == "before":
                assert earliest < index, f"{code} scheduled before its prerequisite"
            else:
                assert earliest <= index, f"{code} scheduled before its corequisite"


# --- Prerequisite ordering ---------------------------------------------------------

def test_chain_is_scheduled_in_order():
    graph = make_graph({"A": 3, "B": 3, "C": 3, "D": 3},
                       {"B": [["A"]], "C": [["B"]], "D": [["C"]]})
    tree = [req("core", "all_courses", ["D", "C", "B", "A"], graph=graph)]
    result = plan(tree, graph, max_credits=12)
    assert_valid(result, graph, 12)
    # Even with room for all four in one term, the chain needs four terms.
    assert [[c["code"] for c in t["courses"]] for t in result["terms"]] == [["A"], ["B"], ["C"], ["D"]]
    assert result["projected_graduation"] == "Spring 2028"


def test_prerequisite_not_required_by_degree_is_added():
    graph = make_graph({"BASE": 3, "ADV": 3}, {"ADV": [["BASE"]]})
    tree = [req("core", "all_courses", ["ADV"], graph=graph)]
    result = plan(tree, graph)
    where = term_index(result)
    assert where["BASE"] < where["ADV"]
    base = next(c for t in result["terms"] for c in t["courses"] if c["code"] == "BASE")
    assert base["satisfies"][0]["name"] == "Prerequisite for a later course"


def test_multiple_prerequisites_and_alternatives():
    graph = make_graph({"A": 3, "B": 3, "X": 3, "Y": 3, "C": 3},
                       {"C": [["A"], ["B"], ["X", "Y"]], "X": [["A"]]})
    tree = [req("core", "all_courses", ["C"], graph=graph)]
    result = plan(tree, graph, max_credits=15)
    assert_valid(result, graph, 15)
    planned = set(term_index(result))
    # Y has no prerequisites, so it's chosen over X.
    assert planned == {"A", "B", "Y", "C"}


def test_corequisite_can_share_a_term():
    graph = make_graph({"LEC": 3, "LAB": 1}, {"LAB": [(["LEC"], "concurrent")]})
    tree = [req("core", "all_courses", ["LEC", "LAB"], graph=graph)]
    result = plan(tree, graph)
    assert_valid(result, graph, 9)
    assert len(result["terms"]) == 1


def test_completed_prerequisites_are_not_replanned():
    graph = make_graph({"A": 3, "B": 3}, {"B": [["A"]]})
    tree = [req("core", "all_courses", ["A", "B"], graph=graph)]
    result = plan(tree, graph, completed={"A": "B"})
    assert [[c["code"] for c in t["courses"]] for t in result["terms"]] == [["B"]]


def test_circular_prerequisites_are_reported():
    graph = make_graph({"A": 3, "B": 3}, {"A": [["B"]], "B": [["A"]]})
    tree = [req("core", "all_courses", ["A", "B"], graph=graph)]
    result = plan(tree, graph)
    assert {u["code"] for u in result["unscheduled"]} == {"A", "B"}
    assert result["projected_graduation"] is None


# --- Credit limits -----------------------------------------------------------------

@pytest.mark.parametrize("max_credits", [3, 6, 7, 12, 15])
def test_credit_limit_is_never_exceeded(max_credits):
    credits = {f"C{i}": 3 for i in range(8)} | {"L1": 4, "L2": 1}
    graph = make_graph(credits, {"C5": [["C1"]], "C6": [["C5"]]})
    tree = [req("core", "all_courses", list(credits), graph=graph)]
    result = plan(tree, graph, max_credits=max_credits)
    assert_valid(result, graph, max_credits)
    if max_credits >= 4:
        assert result["unscheduled"] == []
        assert sum(t["credits"] for t in result["terms"]) == sum(credits.values())


def test_course_larger_than_limit_is_unscheduled():
    graph = make_graph({"BIG": 4, "A": 3})
    tree = [req("core", "all_courses", ["BIG", "A"], graph=graph)]
    result = plan(tree, graph, max_credits=3)
    [unscheduled] = result["unscheduled"]
    assert unscheduled["code"] == "BIG"
    assert "exceeds" in unscheduled["reason"]
    assert result["projected_graduation"] is None


def test_credit_standing_restriction():
    graph = make_graph({"A": 3, "B": 3, "C": 3, "CAP": 3})
    tree = [req("core", "all_courses", ["A", "B", "C", "CAP"], graph=graph)]
    result = plan(tree, graph, max_credits=6,
                  rules_=rules({"CAP": {"min_credits": 9}}), unverified=0)
    where = term_index(result)
    # 0 credits earned at the start; 6 after term 1; 9 only after term 2.
    assert where["CAP"] == 2
    cap = next(c for t in result["terms"] for c in t["courses"] if c["code"] == "CAP")
    assert "Requires 9 earned credits" in cap["notes"]


# --- Choosing courses ----------------------------------------------------------------

def test_required_courses_before_electives():
    graph = make_graph({"R1": 3, "R2": 3, "E1": 3, "E2": 3})
    tree = [req("major", "all_children", children=[
        req("core", "all_courses", ["R1", "R2"], graph=graph),
        req("electives", "min_credits", ["E1", "E2"], min_credits=6, graph=graph),
    ])]
    result = plan(tree, graph, max_credits=6)
    assert [[c["code"] for c in t["courses"]] for t in result["terms"]] == [["R1", "R2"], ["E1", "E2"]]


def test_only_needed_electives_are_planned():
    graph = make_graph({"E1": 3, "E2": 3, "E3": 3, "E4": 3, "PRE": 3}, {"E1": [["PRE"]]})
    tree = [req("electives", "min_credits", ["E1", "E2", "E3", "E4"], min_credits=6, graph=graph)]
    result = plan(tree, graph)
    # Two electives, and not E1 (it would need an extra prerequisite).
    assert set(term_index(result)) == {"E2", "E3"}


def test_course_filling_two_requirements_is_preferred():
    graph = make_graph({"X": 3, "Y": 3, "BOTH": 3})
    tree = [
        req("first", "min_courses", ["X", "BOTH"], min_courses=1, allocation_group=None, graph=graph),
        req("second", "min_courses", ["Y", "BOTH"], min_courses=1, allocation_group=None, graph=graph),
    ]
    result = plan(tree, graph)
    assert set(term_index(result)) == {"BOTH"}


def test_restricted_and_overlapping_courses_are_skipped():
    graph = make_graph({"OTHER_MAJOR": 3, "SAME_AS_DONE": 3, "DONE": 3, "OK": 3})
    tree = [req("electives", "min_courses", ["OTHER_MAJOR", "SAME_AS_DONE", "OK"],
                min_courses=1, graph=graph)]
    r = rules({"OTHER_MAJOR": {"programs": ["Another Major"]}},
              [("SAME_AS_DONE", "DONE", "credit_overlap")])
    result = plan(tree, graph, completed={"DONE": "A"}, rules_=r)
    assert set(term_index(result)) == {"OK"}


def test_requirement_without_catalog_course_gets_a_placeholder():
    graph = make_graph({"A": 3})
    tree = [req("writing", "min_courses", [], min_courses=1, graph=graph)]
    result = plan(tree, graph)
    [course] = result["terms"][0]["courses"]
    assert course["code"] is None
    assert course["kind"] == "placeholder"
    assert course["name"] == "Choose a course: writing"


def test_general_electives_fill_total_credits():
    graph = make_graph({"A": 3, "B": 3})
    tree = [req("degree", "all_children", allocation_group=None, children=[
        req("core", "all_courses", ["A", "B"], graph=graph),
        req("total", "min_credits", ["A", "B"], min_credits=20, any_course=True,
            allocation_group=None, graph=graph),
    ])]
    result = plan(tree, graph, completed={"A": "A"}, max_credits=9)
    assert_valid(result, graph, 9)
    assert result["credits"]["total"] == 20
    electives = [c for t in result["terms"] for c in t["courses"] if c["kind"] == "elective"]
    assert sum(c["credits"] for c in electives) == 14  # 20 - 3 done - 3 for B


def test_already_complete():
    graph = make_graph({"A": 3})
    tree = [req("core", "all_courses", ["A"], graph=graph)]
    result = plan(tree, graph, completed={"A": "A"})
    assert result["terms"] == []
    assert result["graduation_note"] == "Every tracked requirement is already met."


def test_terms_skip_winter_and_summer():
    assert next_term("Fall 2026") == "Spring 2027"
    assert next_term("Spring 2027") == "Fall 2027"
    assert next_term("Summer 2027") == "Fall 2027"
    assert next_term("Winter 2027") == "Spring 2027"
    graph = make_graph({"A": 3})
    tree = [req("core", "all_courses", ["A"], graph=graph)]
    assert plan(tree, graph, start="Summer 2027")["terms"][0]["term"] == "Fall 2027"


def test_earliest_possible_note():
    graph = make_graph({f"C{i}": 3 for i in range(6)})
    tree = [req("core", "all_courses", [f"C{i}" for i in range(6)], graph=graph)]
    result = plan(tree, graph, max_credits=9)
    assert len(result["terms"]) == 2
    assert result["graduation_note"].startswith("Earliest possible")


# --- Real data ------------------------------------------------------------------------

client = TestClient(app)


def recommended_terms(rec):
    """Group a recommendation's additions and slots by term, in order."""
    terms = {}
    for c in rec["additions"] + rec["slots"]:
        terms.setdefault(c["term"], []).append(c)
    order = sorted(terms, key=lambda t: (int(t.split()[1]), t.startswith("Fall")))
    return [{"term": t, "courses": terms[t], "credits": sum(c["credits"] for c in terms[t])}
            for t in order]


@pytest.mark.parametrize("max_credits", [12, 15, 18])
def test_real_recommendation_is_valid(max_credits):
    session = client.post("/api/sessions", json={
        "program_slug": "umd-information-science", "reported_credits": 61,
        "current_term": "Fall 2026", "max_credits_per_term": max_credits}).json()
    try:
        for code in ["MATH115", "PSYC100", "STAT100", "INST126", "INST201", "INST327"]:
            client.post(f"/api/sessions/{session['id']}/courses", json={"code": code, "grade": "B"})
        response = client.post(f"/api/sessions/{session['id']}/plan/recommendation")
        assert response.status_code == 200
        rec = response.json()
        # A recommendation isn't saved.
        assert client.get(f"/api/sessions/{session['id']}/plan").json()["terms"] == []
    finally:
        client.delete(f"/api/sessions/{session['id']}")

    assert "not an official UMD" in rec["disclaimer"]
    assert rec["unscheduled"] == []
    assert any("reported credits" in a for a in rec["assumptions"])
    assert rec["projected_graduation"] is not None

    terms = recommended_terms(rec)
    where = {c["code"]: i for i, t in enumerate(terms) for c in t["courses"] if c["code"]}
    for t in terms:
        assert t["credits"] <= max_credits
    # Core courses are all recommended, and prerequisites come first.
    for code in ["INST311", "INST314", "INST326", "INST335", "INST346", "INST352", "INST362", "INST490"]:
        assert code in where
    assert where["INST326"] < where["INST346"]
    assert all(where[c] < where["INST490"] for c in ["INST346", "INST352", "INST362"])

    # INST490 needs 90 earned credits before its term. Only the 18 recorded
    # credits count; the rest of the reported 61 is unverified.
    earned = 18
    for i, t in enumerate(terms):
        if i == where["INST490"]:
            assert earned >= 90
        earned += t["credits"]

    # Courses for other programs or another campus aren't recommended.
    for code in ["INST301", "INST367", "INST380", "INST454"]:
        assert code not in where


# --- Student changes (pins and removals) ---------------------------------------------

def courses_by_term(result):
    return [[c["code"] for c in t["courses"]] for t in result["terms"]]


def test_moving_a_course_reschedules_its_dependents():
    graph = make_graph({"A": 3, "B": 3, "C": 3}, {"B": [["A"]], "C": [["B"]]})
    tree = [req("core", "all_courses", ["A", "B", "C"], graph=graph)]
    graph_plan = lambda pinned: build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, pinned)
    assert courses_by_term(graph_plan({})) == [["A"], ["B"], ["C"]]
    # What if A waits until Spring 2027?
    result = graph_plan({"A": "Spring 2027"})
    assert courses_by_term(result) == [["A"], ["B"], ["C"]]
    assert [t["term"] for t in result["terms"]] == ["Spring 2027", "Fall 2027", "Spring 2028"]
    assert result["projected_graduation"] == "Spring 2028"
    assert result["warnings"] == []
    a = result["terms"][0]["courses"][0]
    assert a["pinned"] is True


def test_moving_a_course_too_early_warns():
    graph = make_graph({"A": 3, "B": 3}, {"B": [["A"]]})
    tree = [req("core", "all_courses", ["A", "B"], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, {"B": "Fall 2026"})
    [warning] = result["warnings"]
    assert warning["code"] == "B"
    assert warning["message"] == "Needs A first, but A is planned for Fall 2026."
    assert "warnings" in result["graduation_note"]


def test_pinning_over_the_credit_limit_warns():
    graph = make_graph({f"C{i}": 3 for i in range(4)})
    tree = [req("core", "all_courses", [f"C{i}" for i in range(4)], graph=graph)]
    pinned = {f"C{i}": "Fall 2026" for i in range(4)}
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, pinned)
    assert result["terms"][0]["credits"] == 12
    assert result["terms"][0]["warnings"] == ["12 credits is over your 9-credit limit."]


def test_scheduler_never_overfills_around_pins():
    graph = make_graph({f"C{i}": 3 for i in range(6)})
    tree = [req("core", "all_courses", [f"C{i}" for i in range(6)], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, {"C5": "Fall 2026"})
    assert_valid(result, graph, 9)
    assert "C5" in courses_by_term(result)[0]
    assert result["warnings"] == []


def test_added_course_gets_its_prerequisites():
    graph = make_graph({"A": 3, "PRE": 3, "EXTRA": 3}, {"EXTRA": [["PRE"]]})
    tree = [req("core", "all_courses", ["A"], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, {"EXTRA": "Spring 2027"})
    where = term_index(result)
    assert where["PRE"] < where["EXTRA"] == 1


def test_removing_an_elective_picks_another():
    graph = make_graph({"E1": 3, "E2": 3})
    tree = [req("electives", "min_courses", ["E1", "E2"], min_courses=1, graph=graph)]
    assert set(term_index(plan(tree, graph))) == {"E1"}
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, {}, {"E1"})
    assert set(term_index(result)) == {"E2"}


def test_removing_a_required_course_is_reported():
    graph = make_graph({"R1": 3, "R2": 3})
    tree = [req("core", "all_courses", ["R1", "R2"], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Fall 2026", 9, {}, {"R2"})
    assert set(term_index(result)) == {"R1"}
    assert result["projected_graduation"] is None
    assert "you removed R2" in result["unplanned_requirements"][0]["reason"]


def test_credit_standing_warning_for_early_pin():
    graph = make_graph({"A": 3, "CAP": 3})
    tree = [req("core", "all_courses", ["A", "CAP"], graph=graph)]
    result = build_plan(tree, graph, rules({"CAP": {"min_credits": 30}}), {}, 0,
                        "Fall 2026", 9, {"CAP": "Fall 2026"})
    assert result["warnings"][0]["message"].startswith("Requires 30 earned credits")


# --- Earliest graduation ---------------------------------------------------------------

def test_earliest_graduation_limited_by_credits():
    # 7 independent courses, 9 credits per term: ceil(21 / 9) = 3 terms.
    graph = make_graph({f"C{i}": 3 for i in range(7)})
    tree = [req("core", "all_courses", [f"C{i}" for i in range(7)], graph=graph)]
    result = plan(tree, graph, max_credits=9)
    assert result["projected_graduation"] == "Fall 2027"
    assert result["graduation_note"].startswith("Earliest possible")


def test_earliest_graduation_limited_by_prerequisite_chain():
    # Plenty of room per term, but A -> B -> C takes three terms.
    graph = make_graph({"A": 3, "B": 3, "C": 3, "X": 3}, {"B": [["A"]], "C": [["B"]]})
    tree = [req("core", "all_courses", ["A", "B", "C", "X"], graph=graph)]
    result = plan(tree, graph, max_credits=30)
    assert len(result["terms"]) == 3
    assert result["projected_graduation"] == "Fall 2027"
    assert result["graduation_note"].startswith("Earliest possible")


def test_graduation_delayed_by_credit_standing_is_explained():
    # 18 credits at up to 9 per term could finish in 2 terms, but CAP needs 12
    # earned credits first: term 1 earns 9, so CAP waits for term 3.
    graph = make_graph({"A": 3, "B": 3, "CAP": 3})
    tree = [req("degree", "all_children", allocation_group=None, children=[
        req("core", "all_courses", ["A", "B", "CAP"], graph=graph),
        req("total", "min_credits", ["A", "B", "CAP"], min_credits=18, any_course=True,
            allocation_group=None, graph=graph),
    ])]
    result = plan(tree, graph, max_credits=9, rules_=rules({"CAP": {"min_credits": 12}}))
    assert_valid(result, graph, 9)
    assert term_index(result)["CAP"] == 2
    assert result["projected_graduation"] == "Fall 2027"
    assert result["graduation_note"] == (
        "At least 2 semesters are needed; this plan uses 3 because of credit-standing or "
        "prerequisite timing.")


def test_unreachable_credit_standing_is_reported():
    graph = make_graph({"A": 3, "CAP": 3})
    tree = [req("core", "all_courses", ["A", "CAP"], graph=graph)]
    result = plan(tree, graph, max_credits=9, rules_=rules({"CAP": {"min_credits": 30}}))
    [unscheduled] = result["unscheduled"]
    assert unscheduled["code"] == "CAP"
    assert result["projected_graduation"] is None


def test_start_in_spring():
    graph = make_graph({"A": 3, "B": 3}, {"B": [["A"]]})
    tree = [req("core", "all_courses", ["A", "B"], graph=graph)]
    result = plan(tree, graph, start="Spring 2027")
    assert [t["term"] for t in result["terms"]] == ["Spring 2027", "Fall 2027"]
    assert result["projected_graduation"] == "Fall 2027"


# --- Seasons, offerings and Summer ------------------------------------------------------

def test_courses_are_placed_in_seasons_they_were_offered():
    graph = make_graph({"A": 3, "B": 3}, {"B": [["A"]]})
    tree = [req("core", "all_courses", ["A", "B"], graph=graph)]
    # B has only had Fall sections.
    result = build_plan(tree, graph, rules(), {}, 0, "Spring 2027", 9, None, frozenset(),
                        frozenset(), {"A": {"Spring", "Fall"}, "B": {"Fall"}})
    assert [(t["term"], [c["code"] for c in t["courses"]]) for t in result["terms"]] == [
        ("Spring 2027", ["A"]), ("Fall 2027", ["B"])]
    assert any("Testudo" in n for n in result["terms"][1]["courses"][0]["notes"])


def test_course_without_recent_sections_is_flagged():
    graph = make_graph({"A": 3}, {})
    tree = [req("core", "all_courses", ["A"], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Spring 2027", 9, None, frozenset(),
                        frozenset(), {})
    [course] = result["terms"][0]["courses"]
    assert any("No sections" in u for u in course["uncertain"])


def test_summer_terms_are_used_only_when_included():
    graph = make_graph({"A": 3, "B": 3, "C": 3}, {"B": [["A"]], "C": [["B"]]})
    tree = [req("core", "all_courses", ["A", "B", "C"], graph=graph)]
    without = build_plan(tree, graph, rules(), {}, 0, "Spring 2027", Calendar(9))
    assert [t["term"] for t in without["terms"]] == ["Spring 2027", "Fall 2027", "Spring 2028"]
    with_summer = build_plan(tree, graph, rules(), {}, 0, "Spring 2027", Calendar(9, 3))
    assert [t["term"] for t in with_summer["terms"]] == ["Spring 2027", "Summer 2027",
                                                         "Fall 2027"]


def test_fulfilled_requirements_need_no_courses():
    graph = make_graph({"A": 3, "B": 3}, {})
    tree = [req("core", "all_courses", ["A"], graph=graph),
            req("other", "all_courses", ["B"], graph=graph)]
    result = build_plan(tree, graph, rules(), {}, 0, "Spring 2027", 9, None, frozenset(),
                        frozenset({"other"}))
    assert [c["code"] for t in result["terms"] for c in t["courses"]] == ["A"]
