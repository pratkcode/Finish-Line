"""Generate seed.sql: an idempotent sync of catalog and degree data.

Usage: python3 database/build_seed.py
Then:  backend/.venv/bin/python database/migrate.py   (or: psql -1 -f database/seed.sql)

Inputs:
  data/catalog/*.json      official UMD catalog + Testudo Gen Ed (importer/fetch_catalog.py)
  data/prerequisites.json  hand-curated INST prerequisites
  data/restrictions.json   hand-curated INST (and a few other) restrictions
  data/requirements.json   the degree requirement tree

Other departments' prerequisites and restrictions are structured by the strict
parsers in importer/rules.py; text they can't fully match is kept as text and
marked, never guessed. Checks the data before writing anything, so a typo or
an invented prerequisite or requirement fails loudly.

The generated SQL updates courses by code (never deletes them, so student
records stay valid) and rebuilds the derived tables.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "importer"))
from rules import Unparsed, parse_gen_ed, parse_requisites, parse_restriction  # noqa: E402

DATABASE_DIR = Path(__file__).parent
UNIVERSITY = "University of Maryland, College Park"

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
        if code.startswith("INST") and c["restriction_text"] and code not in restrictions:
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


UNIVERSITY_ID = f"(SELECT id FROM universities WHERE name = {sql(UNIVERSITY)})"

COURSE_COLUMNS = [
    "code", "name", "credits_min", "credits_max", "description", "prerequisite_text",
    "corequisite_text", "prerequisites_complete", "gen_ed_text", "restriction_text",
    "credit_only_granted_for", "catalog_year", "source_url", "prerequisite_status",
    "gen_ed_status", "gen_ed_term", "formerly", "cross_listed_with", "jointly_offered_with",
    "repeatable_to", "recommended", "additional_information",
]


def course_id(code):
    return f"(SELECT id FROM courses WHERE code = {sql(code)} AND university_id = {UNIVERSITY_ID})"


def load_catalog():
    """The official catalog, with field names matching the courses table."""
    data = json.loads((DATABASE_DIR / "data/catalog/courses.json").read_text())
    courses = {}
    for c in data["courses"]:
        courses[c["code"]] = {
            **c,
            "prerequisite_text": c.get("prerequisite"),
            "corequisite_text": c.get("corequisite"),
            "restriction_text": c.get("restriction"),
            "credit_only_granted_for": c.get("credit_only_granted_for"),
            "catalog_year": data["catalog_year"],
        }
    return data, courses


def structure_course_rules(courses, prereqs, restrictions, gen_ed):
    """Prerequisites, restrictions and Gen Ed tags for every course: curated
    where available, otherwise parsed strictly, otherwise text only."""
    known = set(courses)
    groups, statuses, parsed_restrictions, tags, errors = {}, {}, {}, {}, []
    for code, c in courses.items():
        if code in prereqs:
            entry = prereqs[code]
            groups[code] = [{**g, "timing": g.get("timing", "before")} for g in entry["groups"]]
            statuses[code] = ("curated", entry["complete"])
        else:
            pre_status, pre = parse_requisites(c["prerequisite_text"], code, known)
            co_status, co = parse_requisites(c["corequisite_text"], code, known, "concurrent")
            order = ["none", "parsed", "partial", "unstructured"]
            status = max(pre_status, co_status, key=order.index)
            if status == "none" and (pre_status != "none" or co_status != "none"):
                status = "parsed"
            groups[code] = [] if status == "unstructured" else pre + co
            statuses[code] = (status, status in ("parsed", "none"))
        if code in restrictions:
            parsed_restrictions[code] = {**restrictions[code], "source": "curated"}
        else:
            r = parse_restriction(c["restriction_text"], known)
            if r:
                parsed_restrictions[code] = r
        if code in gen_ed:
            try:
                tags[code] = parse_gen_ed(gen_ed[code]["text"])
            except Unparsed as e:
                errors.append(f"{code}: can't parse Gen Ed text {e}")
    return groups, statuses, parsed_restrictions, tags, errors


def build(catalog, courses, departments, programs, prereq_groups, statuses, restrictions,
          gen_ed, gen_ed_data, requirements):
    lines = [
        "-- GENERATED by database/build_seed.py. Don't edit; edit data/ and re-run it.",
        f"-- Catalog: {catalog['source']} ({catalog['catalog_year']}, retrieved {catalog['retrieved']})",
        f"-- Gen Ed: {gen_ed_data['source']} terms {', '.join(gen_ed_data['terms'])}",
        "-- Idempotent: run inside one transaction (migrate.py does; or psql -1 -f seed.sql).",
        "-- Courses are updated by code and never deleted, so student records stay valid.",
        "",
        f"INSERT INTO universities (name) VALUES ({sql(UNIVERSITY)}) ON CONFLICT (name) DO NOTHING;",
        "",
        "-- Majors from the catalog. Only those with a requirement tree are 'verified'.",
        "INSERT INTO programs (university_id, slug, name, catalog_url, requirements_status)",
        f"SELECT {UNIVERSITY_ID}, p.slug, p.name, p.url, p.status FROM (VALUES",
        ",\n".join(f"    ({sql(p['slug'])}, {sql(p['name'])}, {sql(p['catalog_url'])}, "
                   f"{sql('verified' if p['slug'] in requirements else 'not_available')})"
                   for p in programs),
        ") AS p (slug, name, url, status)",
        "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, catalog_url = EXCLUDED.catalog_url,",
        "    requirements_status = EXCLUDED.requirements_status;",
        "",
        "INSERT INTO departments (university_id, code, name)",
        f"SELECT {UNIVERSITY_ID}, d.code, d.name FROM (VALUES",
        ",\n".join(f"    ({sql(code)}, {sql(d['name'])})" for code, d in sorted(departments.items())),
        ") AS d (code, name)",
        "ON CONFLICT (university_id, code) DO UPDATE SET name = EXCLUDED.name;",
        "",
        f"CREATE TEMP TABLE import_courses ({', '.join(c + (' INTEGER' if c.startswith('credits') else ' BOOLEAN' if c == 'prerequisites_complete' else ' TEXT') for c in COURSE_COLUMNS)}) ON COMMIT DROP;",
        f"INSERT INTO import_courses ({', '.join(COURSE_COLUMNS)}) VALUES",
    ]
    rows = []
    for code, c in courses.items():
        status, complete = statuses[code]
        tag_text = gen_ed_data["courses"].get(code, {})
        values = {**c, "prerequisites_complete": complete, "prerequisite_status": status,
                  "gen_ed_text": tag_text.get("text"), "gen_ed_term": tag_text.get("term"),
                  "gen_ed_status": "verified" if code in gen_ed else "none_found"}
        rows.append("    (" + ", ".join(sql(values.get(col)) for col in COURSE_COLUMNS) + ")")
    lines.append(",\n".join(rows) + ";")
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in COURSE_COLUMNS if col != "code")
    lines += [
        f"INSERT INTO courses (university_id, {', '.join(COURSE_COLUMNS)})",
        f"SELECT {UNIVERSITY_ID}, * FROM import_courses",
        f"ON CONFLICT (university_id, code) DO UPDATE SET {updates}, in_current_catalog = TRUE;",
        "-- Courses no longer in the catalog are kept for students who completed them.",
        f"UPDATE courses SET in_current_catalog = FALSE WHERE university_id = {UNIVERSITY_ID}",
        "    AND code NOT IN (SELECT code FROM import_courses);",
        "",
        "-- Derived data is rebuilt. No student data references these tables.",
        f"DELETE FROM prerequisite_groups WHERE course_id IN (SELECT id FROM courses WHERE university_id = {UNIVERSITY_ID});",
        f"DELETE FROM course_gen_ed WHERE course_id IN (SELECT id FROM courses WHERE university_id = {UNIVERSITY_ID});",
        f"DELETE FROM course_restrictions WHERE course_id IN (SELECT id FROM courses WHERE university_id = {UNIVERSITY_ID});",
        f"DELETE FROM course_exclusions WHERE course_id IN (SELECT id FROM courses WHERE university_id = {UNIVERSITY_ID});",
        f"DELETE FROM requirements WHERE university_id = {UNIVERSITY_ID}",
        f"    OR program_id IN (SELECT id FROM programs WHERE university_id = {UNIVERSITY_ID});",
        "",
    ]

    for code, course_groups in prereq_groups.items():
        for group in course_groups:
            options = ", ".join(sql(option) for option in group["options"])
            lines += [
                "WITH g AS (",
                "    INSERT INTO prerequisite_groups (course_id, timing, min_grade)",
                f"    VALUES ({course_id(code)}, {sql(group['timing'])}, {sql(group['min_grade'])})",
                "    RETURNING id",
                ")",
                "INSERT INTO prerequisite_options (group_id, course_id)",
                f"SELECT g.id, c.id FROM g, courses c WHERE c.university_id = {UNIVERSITY_ID} AND c.code IN ({options});",
            ]

    tag_rows = [f"    ({sql(code)}, {sql(t['tag'])}, {sql(t['condition'])})"
                for code, course_tags in gen_ed.items()
                for t in {t["tag"]: t for t in course_tags}.values()]
    lines += [
        "",
        "INSERT INTO course_gen_ed (course_id, tag, condition_text)",
        f"SELECT c.id, t.tag, t.condition FROM courses c JOIN (VALUES",
        ",\n".join(tag_rows),
        f") AS t (code, tag, condition) ON t.code = c.code AND c.university_id = {UNIVERSITY_ID};",
        "",
    ]

    for code, r in restrictions.items():
        programs = r.get("programs")
        programs_sql = ("ARRAY[" + ", ".join(sql(p) for p in programs) + "]") if programs else "NULL"
        lines.append(
            "INSERT INTO course_restrictions (course_id, min_credits_earned, programs, "
            "other_conditions, avoid_in_plan, source) "
            f"VALUES ({course_id(code)}, {sql(r.get('min_credits'))}, {programs_sql}, "
            f"{sql(r.get('other'))}, {sql(r.get('avoid_in_plan', False))}, {sql(r['source'])});"
        )
    exclusions = {(a, b, "credit_overlap") for a, b in credit_overlaps(courses)}
    exclusions |= {(code, other, "not_after") for code, r in restrictions.items()
                   for other in r.get("not_after", []) if other != code}
    lines += [
        "",
        "INSERT INTO course_exclusions (course_id, other_course_id, kind)",
        f"SELECT a.id, b.id, e.kind FROM (VALUES",
        ",\n".join(f"    ({sql(a)}, {sql(b)}, {sql(k)})" for a, b, k in sorted(exclusions)),
        ") AS e (course, other, kind)",
        f"JOIN courses a ON a.code = e.course AND a.university_id = {UNIVERSITY_ID}",
        f"JOIN courses b ON b.code = e.other AND b.university_id = {UNIVERSITY_ID};",
        "",
    ]

    for owner, rows in requirements.items():
        for row in rows:
            if row["parent"]:
                parent, university, program = f"(SELECT id FROM requirements WHERE key = {sql(row['parent'])})", "NULL", "NULL"
            elif owner == "university":
                parent, university, program = "NULL", UNIVERSITY_ID, "NULL"
            else:
                parent, university, program = "NULL", "NULL", f"(SELECT id FROM programs WHERE slug = {sql(owner)})"
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
                lines.append(f"SELECT {req_id}, id FROM courses WHERE university_id = {UNIVERSITY_ID} AND code IN ({codes});")
            for f in row.get("filters", []):
                lines.append("INSERT INTO requirement_course_filters (requirement_id, subject, min_number, max_number, gen_ed)")
                lines.append(f"VALUES ({req_id}, " + ", ".join(sql(f.get(k)) for k in ("subject", "min_number", "max_number", "gen_ed")) + ");")
            lines.append("")
    return "\n".join(lines)


def main():
    catalog, courses = load_catalog()
    departments = json.loads((DATABASE_DIR / "data/catalog/departments.json").read_text())["departments"]
    gen_ed_data = json.loads((DATABASE_DIR / "data/catalog/gen_ed.json").read_text())
    prereqs = json.loads((DATABASE_DIR / "data/prerequisites.json").read_text())["courses"]
    requirement_data = json.loads((DATABASE_DIR / "data/requirements.json").read_text())
    restrictions = json.loads((DATABASE_DIR / "data/restrictions.json").read_text())["courses"]
    sources = requirement_data["_format"]["sources"]
    programs = json.loads((DATABASE_DIR / "data/catalog/programs.json").read_text())["programs"]
    # "university" applies to every major; the others are keyed by program slug.
    requirements = {"university": list(flatten_requirements(requirement_data["university"], sources))}
    for slug, tree in requirement_data["programs"].items():
        requirements[slug] = list(flatten_requirements(tree, sources))

    errors = validate(courses, prereqs)
    errors += validate_requirements(courses, [row for rows in requirements.values() for row in rows])
    known_programs = {p["slug"] for p in programs}
    errors += [f"requirements for unknown program {slug}"
               for slug in requirement_data["programs"] if slug not in known_programs]
    errors += validate_restrictions(courses, restrictions)
    errors += [f"{code}: department {code[:4]} not in departments.json"
               for code in courses if code[:4] not in departments]
    errors += [f"{code}: Gen Ed listed for a course not in the catalog"
               for code in gen_ed_data["courses"] if code not in courses]
    groups, statuses, structured_restrictions, gen_ed, rule_errors = structure_course_rules(
        courses, prereqs, restrictions, gen_ed_data["courses"])
    errors += rule_errors
    if errors:
        raise SystemExit("Invalid data:\n  " + "\n  ".join(errors))

    (DATABASE_DIR / "seed.sql").write_text(build(
        catalog, courses, departments, programs, groups, statuses, structured_restrictions, gen_ed,
        gen_ed_data, requirements))
    count = lambda status: sum(1 for s, _ in statuses.values() if s == status)  # noqa: E731
    total_groups = sum(len(g) for g in groups.values())
    print(f"Wrote seed.sql: {len(courses)} courses in {len(departments)} departments, "
          f"{len(programs)} majors ({len(requirement_data['programs'])} with verified requirements), "
          f"{total_groups} prerequisite groups, "
          f"{sum(len(r) for r in requirements.values())} requirements")
    print(f"  prerequisites: {count('curated')} curated, {count('parsed')} parsed, "
          f"{count('partial')} partial, {count('unstructured')} text only, {count('none')} none")
    print(f"  Gen Ed: {len(gen_ed)} courses tagged; "
          f"{sum(1 for t in gen_ed.values() for x in t if x['condition'])} conditional tags not counted")
    print(f"  restrictions: {sum(1 for r in structured_restrictions.values() if r['source'] != 'text_only')} "
          f"structured, {sum(1 for r in structured_restrictions.values() if r['source'] == 'text_only')} text only")


if __name__ == "__main__":
    main()
