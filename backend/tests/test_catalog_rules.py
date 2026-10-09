"""Unit tests for the strict catalog-text parsers (database/importer/rules.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "database" / "importer"))
from rules import Unparsed, parse_gen_ed, parse_list, parse_requisites, parse_restriction  # noqa: E402

KNOWN = {"MATH140", "MATH141", "CMSC131", "CMSC132", "SPAN303", "SPAN311", "SPAN316",
         "PSYC100", "MATH120", "MATH136", "STAT100", "ARAB202", "ENGL101"}


def options(groups):
    return [(g["options"], g["min_grade"], g["timing"]) for g in groups]


def test_lists():
    assert parse_list("MATH140") == ("and", ["MATH140"])
    assert parse_list("MATH140 and MATH141") == ("and", ["MATH140", "MATH141"])
    assert parse_list("MATH140, MATH141, and CMSC131") == ("and", ["MATH140", "MATH141", "CMSC131"])
    assert parse_list("MATH140, MATH141, or CMSC131") == ("or", ["MATH140", "MATH141", "CMSC131"])
    with pytest.raises(Unparsed):
        parse_list("MATH140 and MATH141 or CMSC131")  # mixed: ambiguous


def test_simple_and_graded_prerequisites():
    assert parse_requisites("MATH140.", "MATH141", KNOWN) == ("parsed", [
        {"options": ["MATH140"], "min_grade": None, "timing": "before"}])
    status, groups = parse_requisites(
        "Minimum grade of C- in CMSC131; and minimum grade of C- in MATH141.", "CMSC132", KNOWN)
    assert status == "parsed"
    assert options(groups) == [(["CMSC131"], "C-", "before"), (["MATH141"], "C-", "before")]


def test_alternatives_and_parenthesized_groups():
    status, groups = parse_requisites("SPAN303; and (SPAN311 or SPAN316).", "SPAN363", KNOWN)
    assert status == "parsed"
    assert options(groups) == [(["SPAN303"], None, "before"),
                               (["SPAN311", "SPAN316"], None, "before")]
    status, groups = parse_requisites(
        "PSYC100; and 1 course with a minimum grade of C- from (MATH120, MATH136, or MATH140).",
        "PSYC200", KNOWN)
    assert status == "parsed"
    assert options(groups)[1] == (["MATH120", "MATH136", "MATH140"], "C-", "before")


def test_concurrent_enrollment():
    status, groups = parse_requisites(
        "Must have completed or be concurrently enrolled in STAT100.", "BSOS233", KNOWN)
    assert options(groups) == [(["STAT100"], None, "before_or_concurrent")]
    assert parse_requisites("ENGL101.", "X", KNOWN, "concurrent")[1][0]["timing"] == "concurrent"


def test_non_course_alternative_is_partial():
    status, groups = parse_requisites("MATH141; or permission of instructor.", "MATH200", KNOWN)
    assert status == "partial"
    assert options(groups) == [(["MATH141"], None, "before")]


def test_unclear_text_is_never_guessed():
    for text in [
        "Must have math eligibility of MATH140 or higher.",       # placement
        "Two English courses beyond Fundamental Studies.",        # no course list
        "MATH140; or MATH141 and CMSC131.",                       # course alternative
        "MATH140 and MATH141 or CMSC131.",                        # mixed and/or
        "MATH999.",                                               # not a catalog course
        "MATH141.",                                               # the course itself
    ]:
        assert parse_requisites(text, "MATH141", KNOWN) == ("unstructured", []), text
    assert parse_requisites(None, "MATH141", KNOWN) == ("none", [])


def test_restrictions():
    assert parse_restriction("Must have earned a minimum of 60 credits.", KNOWN) == {
        "min_credits": 60, "not_after": [], "source": "parsed"}
    assert parse_restriction("Must not have completed ARAB202.", KNOWN)["not_after"] == ["ARAB202"]
    other = parse_restriction("For Computer Science majors only.", KNOWN)
    assert other["source"] == "text_only" and other["avoid_in_plan"] is True
    assert parse_restriction(None, KNOWN) is None


def test_gen_ed_tags_and_conditions():
    assert parse_gen_ed("DSHS, DVUP") == [{"tag": "DSHS", "condition": None},
                                          {"tag": "DVUP", "condition": None}]
    tags = parse_gen_ed("DSNL (if taken with BSCI161) or DSNS")
    assert tags == [{"tag": "DSNL", "condition": "if taken with BSCI161"},
                    {"tag": "DSNS", "condition": None}]
    with pytest.raises(Unparsed):
        parse_gen_ed("XXXX")
