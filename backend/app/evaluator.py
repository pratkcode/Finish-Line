"""Evaluate a student's courses against a requirement tree.

Nothing here knows about any specific degree: the rules come from the
requirements tables (see database/data/requirements.json).
"""

import copy
from typing import Literal

GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P"]
Grade = Literal[tuple(GRADES)]
LETTER_RANK = {grade: rank for rank, grade in enumerate(reversed(GRADES[:-1]))}  # F=0 ... A+=12


def meets_grade(grade: str | None, min_grade: str | None) -> bool:
    if grade is None:  # grade not entered yet: trust that the course was passed
        return True
    if grade == "F":
        return False
    if min_grade is None:
        return True
    if grade == "P":  # Pass-Fail never satisfies a minimum letter grade
        return False
    return LETTER_RANK[grade] >= LETTER_RANK[min_grade]


def evaluate(requirements: list[dict], taken: dict[str, dict],
             fulfilled: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """Return a progress dict for every requirement, keyed by requirement key.

    `requirements` is a list of root nodes; each node has 'children' and
    'eligible' (course codes that can satisfy it, in display order).
    `taken` maps course code -> {"code", "name", "credits", "grade"}; grade may be None.
    `fulfilled` holds keys of requirements met some other verified way (a
    transfer evaluation, waiver, ...): they and everything under them are
    complete without using any courses.
    """
    # Within an allocation group, try the least flexible courses first, so a
    # course that fits many requirements isn't used up where another would do.
    flexibility = {}
    for node in walk(requirements):
        if node["allocation_group"] and not node["children"]:
            for code in node["eligible"]:
                pair = (node["allocation_group"], code)
                flexibility[pair] = flexibility.get(pair, 0) + 1

    results = {}
    used = {}  # allocation group -> set of course codes already counted
    for node in requirements:
        evaluate_node(node, taken, used, flexibility, results, fulfilled)
    return results


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node["children"])


def evaluate_node(node, taken, used, flexibility, results, fulfilled=frozenset()) -> dict:
    if node["key"] in fulfilled:
        for inner in walk([node]):
            results[inner["key"]] = {**progress("complete", [], inner, 0, 0), "fulfilled": True}
        return results[node["key"]]
    rule = node["rule"]
    if rule in ("all_children", "any_child"):
        result = evaluate_group(node, taken, used, flexibility, results, fulfilled)
    else:
        result = evaluate_leaf(node, taken, used, flexibility)
    results[node["key"]] = result
    return result


def evaluate_leaf(node, taken, used, flexibility) -> dict:
    rule, group = node["rule"], node["allocation_group"]
    if rule == "not_tracked":
        return progress("not_tracked", [], node)

    already_used = used.setdefault(group, set()) if group else set()
    candidates = [
        taken[code] for code in node["eligible"]
        if code in taken
        and code not in already_used
        and meets_grade(taken[code]["grade"], node["min_grade"])
    ]
    candidates.sort(key=lambda course: flexibility.get((group, course["code"]), 0))

    if rule in ("all_courses", "course_list"):
        applied = candidates
    elif rule == "min_courses":
        applied = candidates[: node["min_courses"]]
    else:  # min_credits
        applied, credits = [], 0
        for course in candidates:
            if credits >= node["min_credits"]:
                break
            applied.append(course)
            credits += course["credits"]

    # Show applied courses in the requirement's own order.
    order = {code: i for i, code in enumerate(node["eligible"])}
    applied.sort(key=lambda course: order[course["code"]])

    if rule != "course_list":
        already_used.update(course["code"] for course in applied)

    if rule == "course_list":
        return progress("not_tracked", applied, node)
    if rule == "all_courses":
        remaining_courses = len(node["eligible"]) - len(applied)
        return progress(status_for(len(applied), remaining_courses), applied, node,
                        courses_remaining=remaining_courses)
    if rule == "min_courses":
        remaining_courses = max(node["min_courses"] - len(applied), 0)
        return progress(status_for(len(applied), remaining_courses), applied, node,
                        courses_remaining=remaining_courses)
    credits = sum(course["credits"] for course in applied)
    remaining_credits = max(node["min_credits"] - credits, 0)
    return progress(status_for(len(applied), remaining_credits), applied, node,
                    credits_remaining=remaining_credits)


def evaluate_group(node, taken, used, flexibility, results, fulfilled=frozenset()) -> dict:
    if node["rule"] == "all_children":
        children = [evaluate_node(child, taken, used, flexibility, results, fulfilled)
                    for child in node["children"]]
        required = [c for c, child in zip(children, node["children"]) if not child["optional"]]
        return progress(combine_statuses([c["status"] for c in required]), [], node)

    # any_child: try each option on its own copy of `used`, then keep the best.
    best = None
    for child in node["children"]:
        trial_used = copy.deepcopy(used)
        child_results = {}
        result = evaluate_node(child, taken, trial_used, flexibility, child_results, fulfilled)
        results.update(child_results)
        score = (result["status"] == "complete", result["fraction"])
        if best is None or score > best[0]:
            best = (score, trial_used)
    used.clear()
    used.update(best[1])

    child_results = [results[child["key"]] for child in node["children"]]
    statuses = [result["status"] for result in child_results]
    if "complete" in statuses:
        status = "complete"
    elif "in_progress" in statuses or any(r["applied_courses"] for r in child_results):
        status = "in_progress"
    elif all(s == "not_tracked" for s in statuses):
        status = "not_tracked"
    else:
        status = "not_started"
    return progress(status, [], node)


def status_for(applied_count: int, remaining: int) -> str:
    if remaining <= 0:
        return "complete"
    return "in_progress" if applied_count else "not_started"


def combine_statuses(statuses: list[str]) -> str:
    tracked = [s for s in statuses if s != "not_tracked"]
    if not tracked:
        return "not_tracked"
    if all(s == "complete" for s in statuses):
        return "complete"
    if any(s in ("complete", "in_progress") for s in tracked):
        return "in_progress"
    return "not_started"


def progress(status, applied, node, courses_remaining=None, credits_remaining=None) -> dict:
    if node["rule"] == "all_courses":
        total = len(node["eligible"])
        fraction = len(applied) / total if total else 0
    elif node["rule"] == "min_courses":
        fraction = min(len(applied) / node["min_courses"], 1)
    elif node["rule"] == "min_credits":
        fraction = min(sum(c["credits"] for c in applied) / node["min_credits"], 1)
    else:
        fraction = 1.0 if status == "complete" else 0.0
    return {
        "status": status,
        "applied_courses": applied,
        "credits_completed": sum(c["credits"] for c in applied),
        "courses_remaining": courses_remaining,
        "credits_remaining": credits_remaining,
        "fraction": round(fraction, 3),
        "fulfilled": False,  # True when met by a verified fulfillment, not courses
    }
