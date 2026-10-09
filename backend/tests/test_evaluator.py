"""Unit tests for the requirement evaluator, using small made-up trees."""

from app.evaluator import evaluate, meets_grade


def req(key, rule, eligible=(), children=(), **fields):
    return {
        "key": key, "rule": rule, "eligible": list(eligible), "children": list(children),
        "min_courses": None, "min_credits": None, "min_grade": None,
        "allocation_group": None, "optional": False, **fields,
    }


def taken(*entries):
    return {code: {"code": code, "name": code, "credits": credits, "grade": grade}
            for code, grade, credits in entries}


def test_meets_grade():
    assert meets_grade("C-", "C-")
    assert not meets_grade("D+", "C-")
    assert meets_grade("D-", None)
    assert not meets_grade("F", None)
    assert meets_grade("P", None)
    assert not meets_grade("P", "C-")


def test_all_courses():
    tree = [req("core", "all_courses", ["A100", "A200", "A300"])]
    result = evaluate(tree, taken(("A100", "B", 3), ("A300", "A", 3)))["core"]
    assert result["status"] == "in_progress"
    assert [c["code"] for c in result["applied_courses"]] == ["A100", "A300"]
    assert result["courses_remaining"] == 1


def test_min_grade_excludes_low_grades():
    tree = [req("core", "all_courses", ["A100"], min_grade="C-")]
    assert evaluate(tree, taken(("A100", "D", 3)))["core"]["status"] == "not_started"


def test_min_credits_counts_remaining():
    tree = [req("electives", "min_credits", ["E1", "E2", "E3"], min_credits=9)]
    result = evaluate(tree, taken(("E1", "A", 3), ("E3", "B", 3)))["electives"]
    assert result["status"] == "in_progress"
    assert result["credits_remaining"] == 3


def test_allocation_group_prevents_double_counting():
    tree = [
        req("core", "all_courses", ["A300"], allocation_group="major"),
        req("electives", "min_credits", ["A300", "A400"], min_credits=3, allocation_group="major"),
        req("total", "min_credits", ["A300", "A400"], min_credits=6),  # no group: counts all
    ]
    results = evaluate(tree, taken(("A300", "A", 3)))
    assert results["core"]["status"] == "complete"
    assert results["electives"]["status"] == "not_started"
    assert results["total"]["credits_completed"] == 3


def test_least_flexible_course_is_used_first():
    # X fits both slots, Y fits only the first; Y should fill the first slot.
    tree = [
        req("first", "min_courses", ["X", "Y"], min_courses=1, allocation_group="g"),
        req("second", "min_courses", ["X"], min_courses=1, allocation_group="g"),
    ]
    results = evaluate(tree, taken(("X", "A", 3), ("Y", "A", 3)))
    assert results["first"]["applied_courses"][0]["code"] == "Y"
    assert results["second"]["status"] == "complete"


def test_any_child_picks_the_completed_option():
    tree = [req("diversity", "any_child", children=[
        req("two_a", "min_courses", ["A1", "A2"], min_courses=2),
        req("a_and_b", "all_children", children=[
            req("one_a", "min_courses", ["A1", "A2"], min_courses=1),
            req("one_b", "min_courses", ["B1"], min_courses=1),
        ]),
    ])]
    results = evaluate(tree, taken(("A1", "A", 3), ("B1", "A", 3)))
    assert results["two_a"]["status"] == "in_progress"
    assert results["a_and_b"]["status"] == "complete"
    assert results["diversity"]["status"] == "complete"


def test_optional_children_do_not_block_parent():
    tree = [req("major", "all_children", children=[
        req("core", "all_courses", ["A100"]),
        req("cognate", "min_courses", ["C1", "C2"], min_courses=2, optional=True),
    ])]
    assert evaluate(tree, taken(("A100", "A", 3)))["major"]["status"] == "complete"


def test_not_tracked_and_course_list():
    tree = [req("group", "all_children", children=[
        req("done", "all_courses", ["A100"]),
        req("gpa", "not_tracked"),
        req("track", "course_list", ["A100", "A200"]),
    ])]
    results = evaluate(tree, taken(("A100", "A", 3)))
    assert results["gpa"]["status"] == "not_tracked"
    assert results["track"]["status"] == "not_tracked"
    assert [c["code"] for c in results["track"]["applied_courses"]] == ["A100"]
    # Untracked parts keep the parent from claiming it is complete.
    assert results["group"]["status"] == "in_progress"
