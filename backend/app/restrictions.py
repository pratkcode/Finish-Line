"""Enrollment rules from course_restrictions and course_exclusions: whether a
student may take a course (program limits, "credit only granted for",
"can't take after"), and credit-standing requirements."""

from dataclasses import dataclass


@dataclass
class Rules:
    """Course restrictions that decide whether the student may take a course."""

    program_name: str
    restrictions: dict[str, dict]  # code -> {min_credits, programs, other, avoid_in_plan}
    exclusions: list[tuple[str, str, str]]  # (course, other_course, 'credit_overlap'|'not_after')

    def blocked_reason(self, code: str, have: set[str], elective: bool = True) -> str | None:
        r = self.restrictions.get(code, {})
        if r.get("programs") and self.program_name not in r["programs"]:
            return "Restricted to other programs"
        if elective and r.get("avoid_in_plan"):
            return "Not generally open: " + (r.get("other") or "see restrictions")
        for course, other, kind in self.exclusions:
            if course == code and other in have:
                if kind == "credit_overlap":
                    return f"Credit is only granted for one of {code} and {other}"
                return f"Can't be taken after {other}"
        return None

    def min_credits(self, code: str) -> int:
        return self.restrictions.get(code, {}).get("min_credits") or 0

    def notes(self, code: str) -> list[str]:
        r = self.restrictions.get(code, {})
        notes = []
        if r.get("min_credits"):
            notes.append(f"Requires {r['min_credits']} earned credits")
        if r.get("other"):
            notes.append(r["other"])
        return notes


def load_rules(conn, program: dict) -> Rules:
    restrictions = {
        row["code"]: {"min_credits": row["min_credits_earned"], "programs": row["programs"],
                      "other": row["other_conditions"], "avoid_in_plan": row["avoid_in_plan"]}
        for row in conn.execute(
            """
            SELECT c.code, r.min_credits_earned, r.programs, r.other_conditions, r.avoid_in_plan
            FROM course_restrictions r JOIN courses c ON c.id = r.course_id
            WHERE c.university_id = %s
            """,
            (program["university_id"],),
        ).fetchall()
    }
    exclusions = [
        (row["course"], row["other"], row["kind"])
        for row in conn.execute(
            """
            SELECT a.code AS course, b.code AS other, e.kind
            FROM course_exclusions e
            JOIN courses a ON a.id = e.course_id
            JOIN courses b ON b.id = e.other_course_id
            WHERE a.university_id = %s
            """,
            (program["university_id"],),
        ).fetchall()
    ]
    return Rules(program["name"], restrictions, exclusions)
