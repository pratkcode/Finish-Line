"""Strict parsers for catalog prerequisite, restriction, and Gen Ed text.

They structure text only when the WHOLE statement matches a known pattern;
anything else is returned as unparsed, so no prerequisite or restriction is
ever guessed. Pure functions, unit-tested in backend/tests/test_catalog_rules.py.
"""

import re

CODE = r"[A-Z]{4}\d{3}[A-Z]?"
GRADE = r"[ABCD][+-]?"
GEN_ED_TAGS = {"FSAW", "FSPW", "FSOC", "FSMA", "FSAR", "DSHS", "DSHU", "DSNS", "DSNL",
               "DSSP", "SCIS", "DVUP", "DVCC"}


class Unparsed(Exception):
    """The text doesn't fully match a supported pattern."""


def parse_list(text: str, allow_comma_or: bool = False) -> tuple[str, list[str]]:
    """'X', 'X and Y', 'X, Y, and Z' -> ('and', [...]); 'X or Y', 'X, Y, or Z' -> ('or', [...]).

    With allow_comma_or, a plain comma list ('X, Y, Z') is an 'or' list (used
    inside '1 course ... from (X, Y, Z)')."""
    text = text.strip()
    if re.fullmatch(CODE, text):
        return "and", [text]
    for word in ("and", "or"):
        match = re.fullmatch(rf"((?:{CODE}, )*{CODE}),? {word} ({CODE})", text)
        if match:
            return word, match.group(1).split(", ") + [match.group(2)]
    if allow_comma_or and re.fullmatch(rf"(?:{CODE}, )+{CODE}", text):
        return "or", text.split(", ")
    raise Unparsed(text)


def parse_clause(clause: str, default_timing: str) -> list[dict]:
    """One '; '-separated clause -> prerequisite groups."""
    clause = clause.strip().rstrip(".").strip()
    clause = re.sub(r"^and ", "", clause)

    match = re.fullmatch(rf"1 course with a minimum grade of ({GRADE}) from \((.+)\)", clause)
    if match:
        kind, codes = parse_list(match.group(2), allow_comma_or=True)
        if kind != "or" and len(codes) > 1:
            raise Unparsed(clause)
        return [{"options": codes, "min_grade": match.group(1), "timing": default_timing}]

    match = re.fullmatch(r"(?:[Mm]ust have completed or be concurrently enrolled in )(.+)", clause)
    if match:
        timing = "before_or_concurrent"
        rest, grade = match.group(1), None
    else:
        match = re.fullmatch(rf"(?:[Mm]inimum grade of ({GRADE}) in )?(.+)", clause)
        if not match:
            raise Unparsed(clause)
        timing, grade, rest = default_timing, match.group(1), match.group(2)

    rest = rest.strip()
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1]
    kind, codes = parse_list(rest)
    if kind == "or":
        return [{"options": codes, "min_grade": grade, "timing": timing}]
    return [{"options": [code], "min_grade": grade, "timing": timing} for code in codes]


def parse_requisites(text: str | None, code: str, known: set[str],
                     default_timing: str = "before") -> tuple[str, list[dict]]:
    """Return (status, groups) for a prerequisite or corequisite statement.

    status: 'none' (no text), 'parsed' (fully structured), 'partial' (course
    part structured; the text also offers a non-course alternative such as
    permission or placement), or 'unstructured'.
    """
    if not text or not text.strip():
        return "none", []
    text = re.sub(r"\s+", " ", text.strip())
    head, _, alternative = text.partition("; or ")
    status = "parsed"
    if alternative:
        if re.search(CODE, alternative):
            return "unstructured", []  # e.g. "X; or Y and Z": a course alternative we won't guess
        status = "partial"
    try:
        groups = []
        for clause in re.split(r";\s*", head):
            groups += parse_clause(clause, default_timing)
    except Unparsed:
        return "unstructured", []
    codes = {c for g in groups for c in g["options"]}
    if code in codes or not codes <= known:
        return "unstructured", []  # self-reference, or a course not in the catalog
    return status, groups


def parse_restriction(text: str | None, known: set[str]) -> dict | None:
    """Structure the restriction kinds we can check; everything else is kept as text
    and marks the course as not generally open (the planner won't auto-pick it)."""
    if not text:
        return None
    clauses = [c.strip().rstrip(".") for c in re.split(r";\s*(?:and\s+)?", text.strip())]
    result = {"min_credits": None, "not_after": [], "source": "parsed"}
    for clause in clauses:
        match = re.fullmatch(r"[Mm]ust have earned a minimum of (\d+) credits", clause)
        if match:
            result["min_credits"] = int(match.group(1))
            continue
        match = re.fullmatch(r"[Mm]ust not have completed (.+)", clause)
        if match:
            try:
                kind, codes = parse_list(match.group(1))
            except Unparsed:
                break
            if not set(codes) <= known:
                break
            result["not_after"] += codes
            continue
        break
    else:
        return result
    return {"min_credits": None, "not_after": [], "source": "text_only", "other": text,
            "avoid_in_plan": True}


def parse_gen_ed(text: str) -> list[dict]:
    """'DSNL (if taken with BSCI161) or DSNS, SCIS' ->
    [{'tag': 'DSNL', 'condition': 'if taken with BSCI161'}, {'tag': 'DSNS', ...}, ...]"""
    parts = re.findall(r"([A-Z]{4})(?: \(([^)]*)\))?", text)
    tags = [{"tag": tag, "condition": condition or None} for tag, condition in parts]
    rebuilt = re.sub(r"[A-Z]{4}(?: \([^)]*\))?", "T", text)
    if not tags or not re.fullmatch(r"T((, | or )T)*", rebuilt):
        raise Unparsed(text)
    unknown = {t["tag"] for t in tags} - GEN_ED_TAGS
    if unknown:
        raise Unparsed(f"unknown tags {unknown} in {text}")
    return tags
