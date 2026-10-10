"""Academic terms: 'Fall 2026', 'Summer 2027', ... ordered within a calendar year
as Winter, Spring, Summer, Fall."""

from datetime import date

SEASONS = ("Winter", "Spring", "Summer", "Fall")
TERM_PATTERN = r"^(Spring|Summer|Fall|Winter) \d{4}$"
PLAN_TERM_PATTERN = r"^(Spring|Summer|Fall) \d{4}$"  # terms a future plan can use


def parse(term: str) -> tuple[str, int]:
    season, year = term.split()
    return season, int(year)


def ordinal(term: str) -> int:
    season, year = parse(term)
    return year * 4 + SEASONS.index(season)


def next_term(term: str, seasons=("Spring", "Fall")) -> str:
    """The next term after `term` whose season is in `seasons`."""
    value = ordinal(term) + 1
    while SEASONS[value % 4] not in seasons:
        value += 1
    return f"{SEASONS[value % 4]} {value // 4}"


def at_or_after(term: str, seasons=("Spring", "Fall")) -> str:
    """`term` if its season is in `seasons`, else the next one that is."""
    return term if parse(term)[0] in seasons else next_term(term, seasons)


def today_term(today: date | None = None) -> str:
    """Rough mapping of a date to a UMD term."""
    today = today or date.today()
    season = ("Winter" if today.month == 1 else "Spring" if today.month <= 5
              else "Summer" if today.month <= 8 else "Fall")
    return f"{season} {today.year}"
