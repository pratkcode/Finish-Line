"""Download the official UMD course catalog and Gen Ed listings into database/data/catalog/.

Usage: backend/.venv/bin/python database/importer/fetch_catalog.py [--cache DIR]

Sources (official UMD sites only):
  - Undergraduate Catalog, approved courses for every department:
    https://academiccatalog.umd.edu/undergraduate/approved-courses/<dept>/
  - Schedule of Classes (Testudo) Gen Ed listings for recent terms:
    https://app.testudo.umd.edu/soc/gen-ed/<term>/<category>

Writes departments.json, courses.json, gen_ed.json and programs.json (the
undergraduate majors listed in the catalog). With --offerings it also writes
offerings.json: the terms in which each course had sections on Testudo. Nothing is inferred:
fields are copied from the pages, and courses or tags that can't be parsed
are reported, not guessed. Uses only the Python standard library.
"""

import argparse
import datetime
import html
import json
import re
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CATALOG = "https://academiccatalog.umd.edu/undergraduate/approved-courses/"
PROGRAMS = "https://academiccatalog.umd.edu/undergraduate/programs/"
TESTUDO = "https://app.testudo.umd.edu/soc/gen-ed/{term}/{tag}"
OFFERINGS = "https://app.testudo.umd.edu/soc/{term}/{department}"
CATALOG_YEAR = "2026-2027"
# Fall 2025 through Fall 2026 (Testudo term ids: year + month).
GEN_ED_TERMS = ["202508", "202512", "202601", "202605", "202608"]
GEN_ED_TAGS = ["FSAW", "FSPW", "FSOC", "FSMA", "FSAR", "DSHS", "DSHU", "DSNS", "DSNL",
               "DSSP", "SCIS", "DVUP", "DVCC"]
OUT = Path(__file__).resolve().parent.parent / "data" / "catalog"

try:  # some Python installs (e.g. python.org on macOS) ship without root certificates
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def fetch(url: str, cache: Path | None) -> str:
    if cache:
        path = cache / (re.sub(r"[^A-Za-z0-9]+", "_", url) + ".html")
        if path.exists():
            return path.read_text(encoding="utf8")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Finish Line catalog import)"})
    with urllib.request.urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        text = response.read().decode("utf8")
    if cache:
        path.write_text(text, encoding="utf8")
    return text


def clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text).replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_departments(index_html: str) -> dict[str, dict]:
    departments = {}
    for slug, label in re.findall(r'href="/undergraduate/approved-courses/([a-z]+)/">([^<]+)<', index_html):
        match = re.match(r"([A-Z]{4})\s*-\s*(.+)", clean(label))
        if match:
            departments[match[1]] = {"name": match[2].strip(), "slug": slug}
    return departments


def parse_programs(index_html: str) -> list[dict]:
    """Undergraduate majors at College Park, from the catalog's program index."""
    programs = {}
    for path, label in re.findall(r'href="(/undergraduate/colleges-schools/[^"]+-major/)"[^>]*>([^<]+)<',
                                  index_html):
        name = re.sub(r"\s+Major$", "", clean(label))
        slug = "umd-" + path.rstrip("/").split("/")[-1].removesuffix("-major")
        programs[slug] = {"slug": slug, "name": name,
                          "catalog_url": "https://academiccatalog.umd.edu" + path}
    return sorted(programs.values(), key=lambda p: p["name"])


def parse_courses(page_html: str, url: str) -> tuple[list[dict], list[str]]:
    courses, problems = [], []
    if f"{CATALOG_YEAR} Catalog" not in page_html:
        problems.append(f"{url}: not the {CATALOG_YEAR} catalog")
    for block in re.findall(r'<div class="courseblock">(.*?)</div>', page_html, re.S):
        title_match = re.search(r"courseblocktitle[^>]*>(.*?)</p>", block, re.S)
        title = clean(title_match.group(1)) if title_match else ""
        match = re.match(r"^([A-Z]{4}\d{3}[A-Z]?) (.*) \((\d+)(?:-(\d+))? Credits?\)$", title)
        if not match:
            problems.append(f"{url}: can't parse course title {title!r}")
            continue
        description = re.search(r"courseblockdesc[^>]*>(.*?)</p>", block, re.S)
        details = {}
        for extra in re.findall(r"courseblockextra[^>]*>(.*?)</p>", block, re.S):
            labelled = re.match(r"\s*<strong>(.*?):?</strong>(.*)", extra, re.S)
            if labelled:
                key = re.sub(r"[^a-z]+", "_", clean(labelled.group(1)).rstrip(":").lower()).strip("_")
                details[key] = clean(labelled.group(2))
        courses.append({
            "code": match[1],
            "name": match[2],
            "credits_min": int(match[3]),
            "credits_max": int(match[4] or match[3]),
            "description": clean(description.group(1)) if description else None,
            "source_url": url,
            **details,
        })
    return courses, problems


def parse_gen_ed(page_html: str) -> dict[str, str]:
    """Course code -> Gen Ed text as Testudo shows it (e.g. 'DSHS, DVUP')."""
    found = {}
    for match in re.finditer(r'course-id">([A-Z]{4}\d{3}[A-Z]?)<', page_html):
        end = page_html.find('course-id">', match.end())
        block = page_html[match.end(): end if end > 0 else len(page_html)]
        group = re.search(r"gen-ed-codes-group.*?</div>\s*</div>", block, re.S)
        text = clean(group.group(0)) if group else ""
        found[match.group(1)] = re.sub(r"^.*?GenEd\s*:\s*", "", text).replace(" ,", ",").strip()
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, help="Directory to cache downloaded pages")
    parser.add_argument("--offerings", action="store_true",
                        help="Also download which terms each course was offered (slow: ~1,000 pages)")
    args = parser.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)

    departments = parse_departments(fetch(CATALOG, args.cache))
    print(f"{len(departments)} departments")
    programs = parse_programs(fetch(PROGRAMS, args.cache))
    print(f"{len(programs)} majors")

    def department_courses(code):
        url = f"{CATALOG}{departments[code]['slug']}/"
        return parse_courses(fetch(url, args.cache), url)

    courses, problems = {}, []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for found, issues in pool.map(department_courses, sorted(departments)):
            problems += issues
            for course in found:
                if course["code"] in courses:
                    problems.append(f"duplicate course {course['code']}")
                else:
                    courses[course["code"]] = course
    print(f"{len(courses)} courses")

    def gen_ed_listing(pair):
        term, tag = pair
        return term, parse_gen_ed(fetch(TESTUDO.format(term=term, tag=tag), args.cache))

    seen: dict[str, dict[str, str]] = {}
    pairs = [(term, tag) for term in GEN_ED_TERMS for tag in GEN_ED_TAGS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for term, listing in pool.map(gen_ed_listing, pairs):
            for code, text in listing.items():
                seen.setdefault(code, {})[term] = text
    # The most recent term a course appeared in is authoritative.
    gen_ed = {
        code: {"text": terms[max(terms)], "term": max(terms)}
        for code, terms in sorted(seen.items()) if code in courses
    }
    not_in_catalog = sorted(code for code in seen if code not in courses)
    print(f"{len(gen_ed)} courses with Gen Ed tags; {len(not_in_catalog)} Testudo codes "
          "aren't catalog courses (section variants) and were skipped")

    retrieved = datetime.date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "departments.json").write_text(json.dumps(
        {"source": CATALOG, "catalog_year": CATALOG_YEAR, "retrieved": retrieved,
         "departments": departments}, indent=1, ensure_ascii=False))
    (OUT / "courses.json").write_text(json.dumps(
        {"source": CATALOG, "catalog_year": CATALOG_YEAR, "retrieved": retrieved,
         "courses": [courses[c] for c in sorted(courses)]}, indent=1, ensure_ascii=False))
    (OUT / "programs.json").write_text(json.dumps(
        {"source": PROGRAMS, "catalog_year": CATALOG_YEAR, "retrieved": retrieved,
         "programs": programs}, indent=1, ensure_ascii=False))
    (OUT / "gen_ed.json").write_text(json.dumps(
        {"source": "https://app.testudo.umd.edu/soc/gen-ed/", "terms": GEN_ED_TERMS,
         "retrieved": retrieved, "skipped_codes_not_in_catalog": not_in_catalog,
         "courses": gen_ed}, indent=1, ensure_ascii=False))

    if args.offerings:
        def department_offerings(pair):
            term, department = pair
            page = fetch(OFFERINGS.format(term=term, department=department), args.cache)
            return term, set(re.findall(r'course-id">([A-Z]{4}\d{3}[A-Z]?)<', page))

        offered: dict[str, set[str]] = {}
        pairs = [(term, dept) for term in GEN_ED_TERMS for dept in sorted(departments)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for term, codes in pool.map(department_offerings, pairs):
                for code in codes:
                    if code in courses:
                        offered.setdefault(code, set()).add(term)
        (OUT / "offerings.json").write_text(json.dumps(
            {"source": "https://app.testudo.umd.edu/soc/", "terms": GEN_ED_TERMS,
             "retrieved": retrieved,
             "note": "A course is listed for a term when Testudo showed it with sections that term.",
             "courses": {code: sorted(terms) for code, terms in sorted(offered.items())}},
            indent=1))
        print(f"{len(offered)} courses offered at least once in {', '.join(GEN_ED_TERMS)}")

    for problem in problems:
        print("PROBLEM:", problem, file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
