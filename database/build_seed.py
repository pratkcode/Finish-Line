"""Generate seed.sql from the JSON files in data/.

Usage: python3 database/build_seed.py

Checks the data before writing anything, so a typo or an invented
prerequisite or requirement fails loudly.
"""

import json
import re
from pathlib import Path

DATABASE_DIR = Path(__file__).parent
UNIVERSITY = "University of Maryland, College Park"
PROGRAM = "Information Science"
PROGRAM_SLUG = "umd-information-science"

# The INST catalog entries still cite these old codes; the AAAS catalog lists
# each new code as "Formerly: <old code>".
ALIASES = {"AASP101": "AAAS101", "AASP210": "AAAS210"}

TIMINGS = {"before", "before_or_concurrent", "concurrent"}

GEN_ED_TAGS = {"FSAW", "FSPW", "FSOC", "FSMA", "FSAR", "DSHS", "DSHU", "DSNS", "DSNL",
               "DSSP", "SCIS", "DVUP", "DVCC"}
RULES = {"all_courses", "min_courses", "min_credits", "all_children", "any_child",
         "course_list", "not_tracked"}
GROUP_RULES = {"all_children", "any_child"}
CATEGORIES = {"university", "general_education", "major", "major_benchmark", "major_core",
              "major_elective", "major_cognate"}
FILTER_FIELDS = {"subject", "min_number", "max_number", "gen_ed"}


def gen_ed_tags(text):
    # Testudo lists tags as "DSHU, SCIS" (both apply) or "DSHS or DSNS" (either).
    return re.split(r", | or ", text) if text else []


def flatten_requirements(nodes, sources, parent=None, inherited=None):
    """Yield requirement rows in tree order, with inherited fields resolved."""
    inherited = inherited or {}
    for order, node in enumerate(nodes):
        row = {**inherited, **{k: v for k, v in node.items() if k != "children"}}
        row["parent"] = parent
        row["sort_order"] = order
        row["source_url"] = sources.get(row.get("source"), row.get("source"))
        yield row
        passed_down = {k: row.get(k) for k in ("category", "min_grade", "allocation_group", "source")}
        yield from flatten_requirements(node.get("children", []), sources, node["key"], passed_down)


def validate_restrictions(courses, restrictions):
    errors = []
    for code, c in courses.items():
        if c["restriction_text"] and code not in restrictions:
            errors.append(f"{code}: has restriction text but no entry in restrictions.json")
    for code, r in restrictions.items():
        if code not in courses:
            errors.append(f"{code}: restriction for unknown course")
            continue
        text = (courses[code]["restriction_text"] or "").lower()
        if not text:
            errors.append(f"{code}: restriction entry but no restriction text")
        if r.get("min_credits") and f"minimum of {r['min_credits']} credits" not in text:
            errors.append(f"{code}: min_credits {r['min_credits']} not in the official text")
        for program in r.get("programs") or []:
            if program.lower() not in text:
                errors.append(f"{code}: program '{program}' not in the official text")
        for other in r.get("not_after", []):
            if other not in courses or other.lower() not in text:
                errors.append(f"{code}: not_after {other} unknown or not in the official text")
        if r.get("other") and "avoid_in_plan" not in r:
            errors.append(f"{code}: entries with 'other' must set avoid_in_plan")
    return errors


def credit_overlaps(courses):
    """Pairs from 'Credit only granted for: A or B' where both are known courses."""
    pairs = set()
    for code, c in courses.items():
        group = codes_in(c["credit_only_granted_for"]) & set(courses)
        for a in group:
            for b in group:
                if a != b:
                    pairs.add((a, b))
    return sorted(pairs)


def validate_requirements(courses, rows):
    errors = []
    keys = [row["key"] for row in rows]
    errors += [f"duplicate requirement key {k}" for k in {k for k in keys if keys.count(k) > 1}]
    has_children = {row["parent"] for row in rows}
    for row in rows:
        key, rule = row["key"], row.get("rule")
        if rule not in RULES:
            errors.append(f"{key}: unknown rule {rule}")
        if row.get("category") not in CATEGORIES:
            errors.append(f"{key}: unknown category {row.get('category')}")
        if (rule in GROUP_RULES) != (key in has_children):
            errors.append(f"{key}: only all_children/any_child rules have children")
        if rule == "min_courses" and not row.get("min_courses"):
            errors.append(f"{key}: min_courses rule needs min_courses")
        if rule == "min_credits" and not row.get("min_credits"):
            errors.append(f"{key}: min_credits rule needs min_credits")
        if rule in ("all_courses", "course_list") and not row.get("courses"):
            errors.append(f"{key}: {rule} rule needs courses")
        for code in row.get("courses", []):
            if code not in courses:
                errors.append(f"{key}: course {code} not in courses.json")
        for f in row.get("filters", []):
            if not f or set(f) - FILTER_FIELDS:
                errors.append(f"{key}: bad filter {f}")
            if "gen_ed" in f and f["gen_ed"] not in GEN_ED_TAGS:
                errors.append(f"{key}: unknown Gen Ed tag {f['gen_ed']}")
        if not row["source_url"]:
            errors.append(f"{key}: no source")
    return errors


def codes_in(text):
    codes = set(re.findall(r"\b[A-Z]{4}\d{3}[A-Z]?\b", text or ""))
    return {ALIASES.get(code, code) for code in codes}


def validate(courses, prereqs):
    errors = []
    for code, entry in prereqs.items():
        if code not in courses:
            errors.append(f"{code}: not in courses.json")
            continue
        course = courses[code]
        official = codes_in(course["prerequisite_text"]) | codes_in(course["corequisite_text"])
        listed = set()
        for group in entry["groups"]:
            if group.get("timing", "before") not in TIMINGS:
                errors.append(f"{code}: bad timing {group['timing']}")
            if not group["options"]:
                errors.append(f"{code}: empty group")
            listed |= set(group["options"])
        for option in listed:
            if option not in courses:
                errors.append(f"{code}: option {option} not in courses.json")
            if option not in official:
                errors.append(f"{code}: option {option} is not in the official text")
            if option == code:
                errors.append(f"{code}: lists itself as a prerequisite")
        if entry["complete"] and official - listed:
            errors.append(f"{code}: marked complete but missing {sorted(official - listed)}")
        if not entry["complete"] and not entry.get("note"):
            errors.append(f"{code}: incomplete entries need a note")

    for code, course in courses.items():
        has_text = course["prerequisite_text"] or course["corequisite_text"]
        if code.startswith("INST") and has_text and code not in prereqs:
            errors.append(f"{code}: has prerequisite text but no entry in prerequisites.json")
    return errors


def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def course_id(code):
    return f"(SELECT id FROM courses WHERE code = {sql(code)})"


def build(courses, prereqs, requirements, restrictions, source):
    lines = [
        "-- GENERATED by database/build_seed.py. Edit data/*.json, then re-run it.",
        f"-- Course data: {source}",
        "",
        "BEGIN;",
        "",
        f"INSERT INTO universities (name) VALUES ({sql(UNIVERSITY)});",
        "",
        "INSERT INTO programs (university_id, slug, name)",
        f"SELECT id, {sql(PROGRAM_SLUG)}, {sql(PROGRAM)} FROM universities WHERE name = {sql(UNIVERSITY)};",
        "",
        "INSERT INTO courses (university_id, code, name, credits_min, credits_max, description,",
        "                     prerequisite_text, corequisite_text, prerequisites_complete, gen_ed_text,",
        "                     restriction_text, credit_only_granted_for)",
        "SELECT u.id, c.* FROM universities u, (VALUES",
    ]
    rows = []
    for code, c in courses.items():
        has_text = c["prerequisite_text"] or c["corequisite_text"]
        complete = prereqs[code]["complete"] if code in prereqs else not has_text
        values = [code, c["name"], c["credits_min"], c["credits_max"], c["description"],
                  c["prerequisite_text"], c["corequisite_text"], complete, c["gen_ed"],
                  c["restriction_text"], c["credit_only_granted_for"]]
        rows.append("    (" + ", ".join(sql(v) for v in values) + ")")
    lines.append(",\n".join(rows))
    lines.append(f") AS c WHERE u.name = {sql(UNIVERSITY)};")
    lines.append("")

    for code, entry in prereqs.items():
        for group in entry["groups"]:
            timing = group.get("timing", "before")
            options = ", ".join(sql(option) for option in group["options"])
            lines += [
                "WITH g AS (",
                "    INSERT INTO prerequisite_groups (course_id, timing, min_grade)",
                f"    VALUES ({course_id(code)}, {sql(timing)}, {sql(group['min_grade'])})",
                "    RETURNING id",
                ")",
                "INSERT INTO prerequisite_options (group_id, course_id)",
                f"SELECT g.id, c.id FROM g, courses c WHERE c.code IN ({options});",
                "",
            ]
    gen_ed_rows = [f"    ({sql(code)}, {sql(tag)})"
                   for code, c in courses.items() for tag in gen_ed_tags(c["gen_ed"])]
    lines += [
        "INSERT INTO course_gen_ed (course_id, tag)",
        "SELECT c.id, t.tag FROM courses c JOIN (VALUES",
        ",\n".join(gen_ed_rows),
        ") AS t (code, tag) ON t.code = c.code;",
        "",
    ]

    for code, r in restrictions.items():
        programs = r.get("programs")
        programs_sql = ("ARRAY[" + ", ".join(sql(p) for p in programs) + "]") if programs else "NULL"
        lines.append(
            "INSERT INTO course_restrictions (course_id, min_credits_earned, programs, "
            "other_conditions, avoid_in_plan) "
            f"VALUES ({course_id(code)}, {sql(r.get('min_credits'))}, {programs_sql}, "
            f"{sql(r.get('other'))}, {sql(r.get('avoid_in_plan', False))});"
        )
    exclusions = [(a, b, "credit_overlap") for a, b in credit_overlaps(courses)]
    exclusions += [(code, other, "not_after") for code, r in restrictions.items()
                   for other in r.get("not_after", [])]
    for a, b, kind in exclusions:
        lines.append("INSERT INTO course_exclusions (course_id, other_course_id, kind) "
                     f"VALUES ({course_id(a)}, {course_id(b)}, {sql(kind)});")
    lines.append("")

    for owner, rows in requirements.items():
        for row in rows:
            if row["parent"]:
                parent, university, program = f"(SELECT id FROM requirements WHERE key = {sql(row['parent'])})", "NULL", "NULL"
            elif owner == "university":
                parent, university, program = "NULL", f"(SELECT id FROM universities WHERE name = {sql(UNIVERSITY)})", "NULL"
            else:
                parent, university, program = "NULL", "NULL", f"(SELECT id FROM programs WHERE slug = {sql(PROGRAM_SLUG)})"
            values = [row["key"], row["name"], row.get("description"), row["category"], row["rule"],
                      row.get("min_courses"), row.get("min_credits"), row.get("min_grade"),
                      row.get("allocation_group"), row.get("optional", False), row["sort_order"],
                      row["source_url"]]
            lines += [
                "INSERT INTO requirements (parent_id, university_id, program_id, key, name, description,",
                "    category, rule, min_courses, min_credits, min_grade, allocation_group, optional,",
                "    sort_order, source_url)",
                f"VALUES ({parent}, {university}, {program}, " + ", ".join(sql(v) for v in values) + ");",
            ]
            req_id = f"(SELECT id FROM requirements WHERE key = {sql(row['key'])})"
            if row.get("courses"):
                codes = ", ".join(sql(code) for code in row["courses"])
                lines.append("INSERT INTO requirement_courses (requirement_id, course_id)")
                lines.append(f"SELECT {req_id}, id FROM courses WHERE code IN ({codes});")
            for f in row.get("filters", []):
                lines.append("INSERT INTO requirement_course_filters (requirement_id, subject, min_number, max_number, gen_ed)")
                lines.append(f"VALUES ({req_id}, " + ", ".join(sql(f.get(k)) for k in ("subject", "min_number", "max_number", "gen_ed")) + ");")
            lines.append("")

    lines += ["COMMIT;", ""]
    return "\n".join(lines)


def main():
    course_data = json.loads((DATABASE_DIR / "data/courses.json").read_text())
    prereq_data = json.loads((DATABASE_DIR / "data/prerequisites.json").read_text())
    requirement_data = json.loads((DATABASE_DIR / "data/requirements.json").read_text())
    restrictions = json.loads((DATABASE_DIR / "data/restrictions.json").read_text())["courses"]
    courses = {c["code"]: c for c in course_data["courses"]}
    prereqs = prereq_data["courses"]
    sources = requirement_data["_format"]["sources"]
    requirements = {owner: list(flatten_requirements(requirement_data[owner], sources))
                    for owner in ("university", "program")}

    errors = validate(courses, prereqs)
    errors += validate_requirements(courses, requirements["university"] + requirements["program"])
    errors += validate_restrictions(courses, restrictions)
    for code, c in courses.items():
        for tag in gen_ed_tags(c["gen_ed"]):
            if tag not in GEN_ED_TAGS:
                errors.append(f"{code}: unknown Gen Ed tag {tag}")
    if errors:
        raise SystemExit("Invalid data:\n  " + "\n  ".join(errors))

    (DATABASE_DIR / "seed.sql").write_text(build(courses, prereqs, requirements, restrictions, course_data["source"]))
    groups = sum(len(e["groups"]) for e in prereqs.values())
    total = sum(len(rows) for rows in requirements.values())
    print(f"Wrote seed.sql: {len(courses)} courses, {groups} prerequisite groups, {total} requirements")


if __name__ == "__main__":
    main()
