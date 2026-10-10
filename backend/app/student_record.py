"""What a student has done, in the form every calculation uses.

The degree audit, the semester plan, recommendations, eligibility and the
dashboard all start from `load_student_record`, so they can't disagree about
what counts.

What counts toward requirements:
  - UMD courses marked completed (an F earns no credit and meets no minimum)
  - transfer credit the student marks as verified by UMD: with an equivalent
    UMD course it counts as that course; without one it counts toward total
    credits only
  - requirement fulfillments marked verified or approved exception
What doesn't (shown as pending verification):
  - student-reported transfer credit and fulfillments
  - a reported credit total that isn't matched to recorded courses
In-progress courses are kept apart: they aren't completed, but they will be
before any later semester, so plans treat them as done for prerequisites.
Every course and credit is counted once.
"""

from dataclasses import dataclass, field
from uuid import UUID

from app.sessions import load_session

COUNTED_VERIFICATIONS = ("umd_verified", "approved_exception")


@dataclass
class StudentRecord:
    session: dict
    # UMD course code -> {"grade", "credits", "source"}: counts toward requirements.
    completed: dict[str, dict] = field(default_factory=dict)
    # UMD course code -> {"credits", "source"}: in progress this semester.
    in_progress: dict[str, dict] = field(default_factory=dict)
    # Verified credit without a specific UMD course (counts toward total credits only).
    credit_block: int = 0
    # Requirement keys met by verified fulfillments.
    fulfilled: set[str] = field(default_factory=set)
    # Items shown but not counted: {"kind", "description", "credits", "reason"}.
    pending: list[dict] = field(default_factory=list)
    # UMD codes the student reported as transfer equivalents (not verified yet).
    reported_equivalents: dict[str, str] = field(default_factory=dict)
    earned_credits: int = 0  # all completed credit, as recorded (verified or not)
    applicable_credits: int = 0  # completed credit that counts toward the degree
    in_progress_credits: int = 0
    unrecorded_credits: int = 0  # in the reported total but not recorded as courses

    @property
    def unverified_credits(self) -> int:
        """Credit shown but not counted: student-reported transfer credit, plus
        reported credits not recorded as courses."""
        return self.earned_credits - self.applicable_credits + self.unrecorded_credits


def load_student_record(conn, session_id: UUID, session: dict | None = None) -> StudentRecord:
    session = session or load_session(conn, session_id)
    record = StudentRecord(session=session)

    for c in session["courses"]:
        if c["status"] == "in_progress":
            record.in_progress[c["code"]] = {"credits": c["credits"], "source": "umd"}
            record.in_progress_credits += c["credits"]
            continue
        earned = 0 if c["grade"] == "F" else c["credits"]
        record.completed[c["code"]] = {"grade": c["grade"], "credits": earned, "source": "umd"}
        record.earned_credits += earned
        record.applicable_credits += earned

    transfers = conn.execute(
        """
        SELECT t.id, t.institution, t.kind, t.external_code, t.title, t.credits, t.grade,
               t.status, t.verification, c.code AS equivalent
        FROM transfer_credits t LEFT JOIN courses c ON c.id = t.equivalent_course_id
        WHERE t.session_id = %s ORDER BY t.id
        """,
        (session_id,),
    ).fetchall()
    for t in transfers:
        label = " ".join(x for x in (t["external_code"], t["title"]) if x) or "Transfer credit"
        description = f"{label} ({t['institution']})"
        if t["status"] == "in_progress":
            record.in_progress_credits += t["credits"]
            if t["equivalent"] and t["verification"] == "umd_verified":
                record.in_progress.setdefault(t["equivalent"], {"credits": t["credits"],
                                                                "source": "transfer"})
            continue
        record.earned_credits += t["credits"]
        if t["verification"] != "umd_verified":
            record.pending.append({"kind": "transfer", "description": description,
                                   "credits": t["credits"],
                                   "reason": "Reported by you; not yet verified by UMD"})
            if t["equivalent"]:
                record.reported_equivalents[t["equivalent"]] = description
            continue
        if t["equivalent"]:
            if t["equivalent"] in record.completed:
                # Already counted (e.g. also taken at UMD): count credit once.
                record.pending.append({"kind": "transfer", "description": description,
                                       "credits": t["credits"],
                                       "reason": f"Duplicates {t['equivalent']}, already counted"})
                record.earned_credits -= t["credits"]
                continue
            record.completed[t["equivalent"]] = {"grade": None, "credits": t["credits"],
                                                 "source": "transfer"}
        else:
            record.credit_block += t["credits"]
        record.applicable_credits += t["credits"]

    reported_total = session["credits"]["reported"]
    if reported_total is not None and reported_total > record.earned_credits:
        record.unrecorded_credits = reported_total - record.earned_credits
        record.pending.append({
            "kind": "reported_total",
            "description": "Credits in your reported total that aren't recorded as courses",
            "credits": reported_total - record.earned_credits,
            "reason": "Add them as courses or transfer credit to count them"})

    for f in conn.execute(
        "SELECT f.requirement_key, f.method, f.verification, f.note, "
        "(SELECT r.name FROM requirements r WHERE r.key = f.requirement_key LIMIT 1) AS name "
        "FROM requirement_fulfillments f WHERE f.session_id = %s ORDER BY f.id",
        (session_id,),
    ).fetchall():
        if f["verification"] in COUNTED_VERIFICATIONS:
            record.fulfilled.add(f["requirement_key"])
        else:
            record.pending.append({"kind": "fulfillment",
                                   "description": f["name"] or f["requirement_key"],
                                   "credits": 0,
                                   "reason": "Reported by you; not yet verified or approved"})
    return record


def taken_courses(record: StudentRecord, graph_courses: dict, include_in_progress=False) -> dict:
    """The record as the evaluator's `taken` map (code -> {code, name, credits, grade})."""
    taken = {
        code: {"code": code, "name": graph_courses[code]["name"], "credits": c["credits"],
               "grade": c["grade"]}
        for code, c in record.completed.items() if code in graph_courses
    }
    if include_in_progress:
        for code, c in record.in_progress.items():
            if code in graph_courses and code not in taken:
                taken[code] = {"code": code, "name": graph_courses[code]["name"],
                               "credits": c["credits"], "grade": None}
    return taken
