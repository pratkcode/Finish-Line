"""Prerequisite checks for a student's completed courses.

Prerequisites are stored as groups (see database/schema.sql): every group must
be satisfied, and any one option in a group satisfies it. A group's timing says
whether its course must be done before ('before'), may also be taken the same
semester ('before_or_concurrent'), or must be taken the same semester
('concurrent', a corequisite).

All functions here work on a PrereqGraph, so they can be tested without a
database.
"""

import math
from dataclasses import dataclass

from app.evaluator import meets_grade


@dataclass
class PrereqGraph:
    courses: dict[str, dict]  # code -> {code, name, credits_min, credits_max,
    #                                    prerequisites_complete, prerequisite_text}
    groups: dict[str, list[dict]]  # code -> [{timing, min_grade, options: [code, ...]}]


def load_graph(conn, university_id: int) -> PrereqGraph:
    courses = {
        row["code"]: row
        for row in conn.execute(
            """
            SELECT code, name, credits_min, credits_max, prerequisites_complete,
                   prerequisite_text, corequisite_text
            FROM courses WHERE university_id = %s
            """,
            (university_id,),
        ).fetchall()
    }
    groups: dict[str, list[dict]] = {}
    by_id: dict[int, dict] = {}
    for row in conn.execute(
        """
        SELECT g.id, c.code AS course, g.timing, g.min_grade, o.code AS option
        FROM prerequisite_groups g
        JOIN courses c ON c.id = g.course_id
        JOIN prerequisite_options po ON po.group_id = g.id
        JOIN courses o ON o.id = po.course_id
        WHERE c.university_id = %s
        ORDER BY g.id, o.code
        """,
        (university_id,),
    ).fetchall():
        group = by_id.get(row["id"])
        if group is None:
            group = {"timing": row["timing"], "min_grade": row["min_grade"], "options": []}
            by_id[row["id"]] = group
            groups.setdefault(row["course"], []).append(group)
        group["options"].append(row["option"])
    return PrereqGraph(courses, groups)


class Checker:
    """Answers prerequisite questions for one student's completed courses.

    `completed` maps course code -> grade (None = grade not entered, which is
    assumed to meet any minimum).
    """

    def __init__(self, graph: PrereqGraph, completed: dict[str, str | None],
                 unavailable: frozenset[str] | set[str] = frozenset()):
        self.graph = graph
        self.completed = completed
        # Courses the student can't take (e.g. restricted to other programs);
        # plans route around them when a group has other options.
        self.unavailable = unavailable
        self._available: dict[str, bool] = {}
        self._cost: dict[tuple[str, str | None], float] = {}

    # --- Basic facts ---------------------------------------------------------

    def done(self, code: str, min_grade: str | None) -> bool:
        return code in self.completed and meets_grade(self.completed[code], min_grade)

    def group_met(self, group: dict) -> bool:
        return any(self.done(code, group["min_grade"]) for code in group["options"])

    def available_now(self, code: str) -> bool:
        """True when every 'before' prerequisite is met and every same-semester
        one is met or could be taken alongside."""
        if code not in self._available:
            self._available[code] = False  # guards against cycles
            self._available[code] = all(
                self.group_state(group) != "missing" for group in self.graph.groups.get(code, [])
            )
        return self._available[code]

    def group_state(self, group: dict) -> str:
        if self.group_met(group):
            return "met"
        if group["timing"] != "before" and any(
            code not in self.completed and self.strictly_available(code)
            for code in group["options"]
        ):
            return "concurrent"
        return "missing"

    def strictly_available(self, code: str) -> bool:
        # Available without relying on yet another same-semester course.
        return all(self.group_met(g) for g in self.graph.groups.get(code, []))

    def option_state(self, code: str, min_grade: str | None) -> str:
        if self.done(code, min_grade):
            return "completed"
        if code in self.completed:
            return "low_grade"
        return "available" if self.available_now(code) else "blocked"

    # --- Planning what to take first -----------------------------------------

    def cost(self, code: str, min_grade: str | None = None) -> float:
        """Fewest courses needed to complete `code` (0 if already done)."""
        key = (code, min_grade)
        if self.done(code, min_grade):
            return 0
        if key in self._cost:
            return self._cost[key]
        if code in self.unavailable:
            return math.inf
        self._cost[key] = math.inf  # in progress: a cycle back here is impossible
        total = 1.0
        for group in self.graph.groups.get(code, []):
            if not self.group_met(group):
                total += min(self.cost(o, group["min_grade"]) for o in group["options"])
        self._cost[key] = total
        return total

    def best_option(self, group: dict) -> str:
        # Cheapest option; ties keep catalog order.
        return min(group["options"], key=lambda o: self.cost(o, group["min_grade"]))

    def plan(self, code: str) -> tuple[list[str], list[str]]:
        """Courses to complete before `code` (in a workable order), and courses
        that may instead be taken the same semester as it."""
        before: list[str] = []
        same_term: list[str] = []
        self._collect(code, before, same_term, visiting=set())
        return before, [c for c in same_term if c not in before]

    def _collect(self, code, before, same_term, visiting):
        if code in visiting:
            return
        visiting.add(code)
        for group in self.graph.groups.get(code, []):
            if self.group_met(group):
                continue
            option = self.best_option(group)
            if math.isinf(self.cost(option, group["min_grade"])):
                continue  # unreachable (circular) option: nothing sensible to add
            # The option's own prerequisites always come first.
            self._collect(option, before, same_term, visiting)
            target = same_term if group["timing"] != "before" else before
            if option not in before and option not in target:
                target.append(option)
        visiting.discard(code)

    # --- Full answer for one course ------------------------------------------

    def check(self, code: str, retake: bool = False) -> dict:
        """Status of `code` for this student. With retake=True a course already
        in the completed list (e.g. with too low a grade) is checked as if new."""
        course = self.graph.courses[code]
        groups = []
        for group in self.graph.groups.get(code, []):
            groups.append({
                "timing": group["timing"],
                "min_grade": group["min_grade"],
                "state": self.group_state(group),
                "options": [
                    {**self.ref(o), "state": self.option_state(o, group["min_grade"]),
                     "grade": self.completed.get(o)}
                    for o in group["options"]
                ],
            })

        if code in self.completed and not retake:
            status = "completed"
        elif any(g["state"] == "missing" for g in groups):
            status = "blocked"
        elif any(g["state"] == "concurrent" for g in groups):
            status = "available_with_concurrent"
        else:
            status = "available"

        before, same_term = self.plan(code) if status != "completed" else ([], [])
        return {
            **self.ref(code),
            "status": status,
            "groups": groups,
            "complete_first": [self.ref(c) for c in before],
            "take_with": [self.ref(c) for c in same_term],
            # Catalog conditions that aren't course lists (placement, permission, ...).
            "additional_conditions": None if course["prerequisites_complete"]
            else (course["prerequisite_text"] or course.get("corequisite_text")),
        }

    def ref(self, code: str) -> dict:
        c = self.graph.courses[code]
        return {"code": c["code"], "name": c["name"],
                "credits_min": c["credits_min"], "credits_max": c["credits_max"]}


def prerequisite_tree(graph: PrereqGraph, code: str, path: tuple[str, ...] = ()) -> dict:
    """Every level of prerequisites under `code`, independent of any student."""
    course = graph.courses[code]
    node = {"code": code, "name": course["name"], "credits_min": course["credits_min"],
            "credits_max": course["credits_max"],
            "prerequisites_complete": course["prerequisites_complete"],
            "groups": [], "cycle": code in path}
    if node["cycle"]:
        return node
    for group in graph.groups.get(code, []):
        node["groups"].append({
            "timing": group["timing"],
            "min_grade": group["min_grade"],
            "options": [prerequisite_tree(graph, o, path + (code,)) for o in group["options"]],
        })
    return node
