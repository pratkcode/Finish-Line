"""A student's academic history: semesters (at UMD or elsewhere), transfer
credit, and requirements met by other verified means.

UMD courses themselves are managed by app/sessions.py (/courses), and can be
attached to a UMD semester here. What counts is decided in app/student_record.py.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.courses import normalize_code
from app.db import get_connection
from app.requirements import find_program, load_requirements
from app.sessions import Status, check_terms, load_session
from app.student_record import COUNTED_VERIFICATIONS, load_student_record
from app.terms import TERM_PATTERN, ordinal, today_term

router = APIRouter(prefix="/api/sessions", tags=["academic history"])

UMD = "University of Maryland, College Park"
TransferVerification = Literal["student_reported", "umd_verified"]
FulfillmentVerification = Literal["student_reported", "umd_verified", "approved_exception"]
Method = Literal["transfer_credit", "exam_credit", "waiver", "substitution", "associate_degree",
                 "other"]


# --- Request models -------------------------------------------------------------------

class TermIn(BaseModel):
    term: str = Field(pattern=TERM_PATTERN)
    institution: str | None = Field(None, max_length=200)  # default: UMD
    at_umd: bool = True


class TermUpdate(BaseModel):
    term: str | None = Field(None, pattern=TERM_PATTERN)
    institution: str | None = Field(None, max_length=200)


class TransferIn(BaseModel):
    academic_term_id: int | None = None
    institution: str | None = Field(None, max_length=200)  # default: the semester's institution
    kind: Literal["course", "credits"] = "course"
    external_code: str | None = Field(None, max_length=30)
    title: str | None = Field(None, max_length=200)
    credits: int = Field(ge=0, le=200)
    grade: str | None = Field(None, max_length=10)
    status: Status = "completed"
    equivalent_code: str | None = Field(None, max_length=10)  # a UMD course, if one applies
    verification: TransferVerification = "student_reported"
    verification_note: str | None = Field(None, max_length=500)


class TransferUpdate(BaseModel):
    academic_term_id: int | None = None
    institution: str | None = Field(None, max_length=200)
    external_code: str | None = Field(None, max_length=30)
    title: str | None = Field(None, max_length=200)
    credits: int | None = Field(None, ge=0, le=200)
    grade: str | None = Field(None, max_length=10)
    status: Status | None = None
    equivalent_code: str | None = Field(None, max_length=10)
    verification: TransferVerification | None = None
    verification_note: str | None = Field(None, max_length=500)


class FulfillmentIn(BaseModel):
    requirement_key: str = Field(max_length=100)
    method: Method
    verification: FulfillmentVerification = "student_reported"
    note: str | None = Field(None, max_length=500)
    transfer_credit_id: int | None = None


class FulfillmentUpdate(BaseModel):
    method: Method | None = None
    verification: FulfillmentVerification | None = None
    note: str | None = Field(None, max_length=500)
    transfer_credit_id: int | None = None


# --- Response models ------------------------------------------------------------------

class HistoryCourse(BaseModel):
    code: str
    name: str
    credits: int
    credits_min: int
    credits_max: int
    grade: str | None
    status: Status


class TransferOut(BaseModel):
    id: int
    academic_term_id: int | None
    institution: str
    kind: Literal["course", "credits"]
    external_code: str | None
    title: str | None
    credits: int
    grade: str | None
    status: Status
    equivalent_code: str | None
    equivalent_name: str | None
    verification: TransferVerification
    verification_note: str | None
    counted: bool  # True when it counts toward degree requirements


class HistoryTerm(BaseModel):
    id: int
    term: str
    institution: str
    at_umd: bool
    period: Literal["past", "current", "future"]
    courses: list[HistoryCourse]
    transfers: list[TransferOut]


class FulfillmentOut(BaseModel):
    id: int
    requirement_key: str
    requirement_name: str
    method: Method
    verification: FulfillmentVerification
    note: str | None
    transfer_credit_id: int | None
    counted: bool


class RequirementOption(BaseModel):
    key: str
    name: str
    path: list[str]
    category: str


class PendingItem(BaseModel):
    kind: str
    description: str
    credits: int
    reason: str


class HistorySummary(BaseModel):
    earned_credits: int  # all completed credit you recorded
    applicable_credits: int  # what counts toward the degree
    in_progress_credits: int
    pending: list[PendingItem]  # recorded but not counted, and why


class History(BaseModel):
    current_term: str
    terms: list[HistoryTerm]  # in order
    unassigned_courses: list[HistoryCourse]  # UMD courses without a semester
    unassigned_transfers: list[TransferOut]
    fulfillments: list[FulfillmentOut]
    requirement_options: list[RequirementOption]  # what a fulfillment can apply to
    summary: HistorySummary


# --- Routes -------------------------------------------------------------------------------

@router.get("/{session_id}/history", response_model=History)
def get_history(session_id: UUID):
    with get_connection() as conn:
        return build_history(conn, session_id)


@router.post("/{session_id}/history/terms", response_model=History, status_code=201)
def add_term(session_id: UUID, body: TermIn):
    with get_connection() as conn:
        load_session(conn, session_id)
        institution = UMD if body.at_umd else (body.institution or "").strip()
        if not institution:
            raise HTTPException(status_code=422, detail="Enter the institution's name")
        exists = conn.execute(
            "SELECT 1 FROM academic_terms WHERE session_id = %s AND institution = %s AND term = %s",
            (session_id, institution, body.term)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail=f"{body.term} at {institution} is already recorded")
        conn.execute(
            "INSERT INTO academic_terms (session_id, term, institution, at_umd) VALUES (%s, %s, %s, %s)",
            (session_id, body.term, institution, body.at_umd))
        return build_history(conn, session_id)


@router.patch("/{session_id}/history/terms/{term_id}", response_model=History)
def update_term(session_id: UUID, term_id: int, body: TermUpdate):
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    with get_connection() as conn:
        term = find_term(conn, session_id, term_id)
        if "institution" in changes and term["at_umd"]:
            changes.pop("institution")  # UMD semesters stay at UMD
        if changes:
            columns = ", ".join(f"{c} = %({c})s" for c in changes)
            conn.execute(f"UPDATE academic_terms SET {columns} WHERE id = %(id)s",
                         {**changes, "id": term_id})
            if "institution" in changes:
                conn.execute("UPDATE transfer_credits SET institution = %s WHERE academic_term_id = %s",
                             (changes["institution"], term_id))
        return build_history(conn, session_id)


@router.delete("/{session_id}/history/terms/{term_id}", response_model=History)
def remove_term(session_id: UUID, term_id: int):
    """Remove a semester and every course and transfer entry recorded in it."""
    with get_connection() as conn:
        find_term(conn, session_id, term_id)
        conn.execute("DELETE FROM academic_terms WHERE id = %s", (term_id,))
        return build_history(conn, session_id)


@router.post("/{session_id}/transfer-credits", response_model=History, status_code=201)
def add_transfer(session_id: UUID, body: TransferIn):
    with get_connection() as conn:
        load_session(conn, session_id)
        values = transfer_values(conn, session_id, body.model_dump())
        columns = ", ".join(values)
        conn.execute(
            f"INSERT INTO transfer_credits (session_id, {columns}) "
            f"VALUES (%(session_id)s, {', '.join(f'%({c})s' for c in values)})",
            {**values, "session_id": session_id})
        return build_history(conn, session_id)


@router.patch("/{session_id}/transfer-credits/{transfer_id}", response_model=History)
def update_transfer(session_id: UUID, transfer_id: int, body: TransferUpdate):
    changes = body.model_dump(exclude_unset=True)
    with get_connection() as conn:
        current = find_transfer(conn, session_id, transfer_id)
        merged = {**current, **changes}
        if "equivalent_code" not in changes:
            merged["equivalent_code"] = current["equivalent_code"]
        values = transfer_values(conn, session_id, merged)
        columns = ", ".join(f"{c} = %({c})s" for c in values)
        conn.execute(f"UPDATE transfer_credits SET {columns} WHERE id = %(id)s",
                     {**values, "id": transfer_id})
        return build_history(conn, session_id)


@router.delete("/{session_id}/transfer-credits/{transfer_id}", response_model=History)
def remove_transfer(session_id: UUID, transfer_id: int):
    with get_connection() as conn:
        find_transfer(conn, session_id, transfer_id)
        conn.execute("DELETE FROM transfer_credits WHERE id = %s", (transfer_id,))
        return build_history(conn, session_id)


@router.post("/{session_id}/fulfillments", response_model=History, status_code=201)
def add_fulfillment(session_id: UUID, body: FulfillmentIn):
    with get_connection() as conn:
        options = requirement_options(conn, load_session(conn, session_id))
        if body.requirement_key not in {o["key"] for o in options}:
            raise HTTPException(status_code=404, detail="That requirement isn't part of your degree")
        if body.transfer_credit_id is not None:
            find_transfer(conn, session_id, body.transfer_credit_id)
        exists = conn.execute(
            "SELECT 1 FROM requirement_fulfillments WHERE session_id = %s AND requirement_key = %s",
            (session_id, body.requirement_key)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="That requirement is already recorded as met")
        conn.execute(
            """
            INSERT INTO requirement_fulfillments
                (session_id, requirement_key, method, verification, note, transfer_credit_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, body.requirement_key, body.method, body.verification, body.note,
             body.transfer_credit_id))
        return build_history(conn, session_id)


@router.patch("/{session_id}/fulfillments/{fulfillment_id}", response_model=History)
def update_fulfillment(session_id: UUID, fulfillment_id: int, body: FulfillmentUpdate):
    changes = body.model_dump(exclude_unset=True)
    with get_connection() as conn:
        find_fulfillment(conn, session_id, fulfillment_id)
        for required in ("method", "verification"):
            if required in changes and changes[required] is None:
                raise HTTPException(status_code=422, detail=f"{required} cannot be null")
        if changes.get("transfer_credit_id") is not None:
            find_transfer(conn, session_id, changes["transfer_credit_id"])
        if changes:
            columns = ", ".join(f"{c} = %({c})s" for c in changes)
            conn.execute(f"UPDATE requirement_fulfillments SET {columns} WHERE id = %(id)s",
                         {**changes, "id": fulfillment_id})
        return build_history(conn, session_id)


@router.delete("/{session_id}/fulfillments/{fulfillment_id}", response_model=History)
def remove_fulfillment(session_id: UUID, fulfillment_id: int):
    with get_connection() as conn:
        find_fulfillment(conn, session_id, fulfillment_id)
        conn.execute("DELETE FROM requirement_fulfillments WHERE id = %s", (fulfillment_id,))
        return build_history(conn, session_id)


# --- Helpers -------------------------------------------------------------------------------

def find_term(conn, session_id: UUID, term_id: int) -> dict:
    load_session(conn, session_id)
    term = conn.execute("SELECT * FROM academic_terms WHERE id = %s AND session_id = %s",
                        (term_id, session_id)).fetchone()
    if term is None:
        raise HTTPException(status_code=404, detail="Semester not found")
    return term


def find_transfer(conn, session_id: UUID, transfer_id: int) -> dict:
    load_session(conn, session_id)
    row = conn.execute(
        """
        SELECT t.academic_term_id, t.institution, t.kind, t.external_code, t.title, t.credits,
               t.grade, t.status, c.code AS equivalent_code, t.verification, t.verification_note
        FROM transfer_credits t LEFT JOIN courses c ON c.id = t.equivalent_course_id
        WHERE t.id = %s AND t.session_id = %s
        """,
        (transfer_id, session_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Transfer credit not found")
    return row


def find_fulfillment(conn, session_id: UUID, fulfillment_id: int) -> None:
    load_session(conn, session_id)
    if conn.execute("SELECT 1 FROM requirement_fulfillments WHERE id = %s AND session_id = %s",
                    (fulfillment_id, session_id)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Fulfillment not found")


def transfer_values(conn, session_id: UUID, data: dict) -> dict:
    """Validate a transfer entry and return the column values to store."""
    term = None
    if data.get("academic_term_id") is not None:
        term = find_term(conn, session_id, data["academic_term_id"])
        if term["at_umd"]:
            raise HTTPException(status_code=422, detail=(
                "Transfer credit belongs to a semester at another institution"))
    institution = (term["institution"] if term else (data.get("institution") or "").strip())
    if not institution:
        raise HTTPException(status_code=422, detail="Enter the institution's name")
    kind = data.get("kind") or "course"
    if kind == "course" and not (data.get("external_code") or data.get("title")):
        raise HTTPException(status_code=422, detail="Enter the course code or title")
    if data.get("status") == "in_progress" and data.get("grade"):
        raise HTTPException(status_code=422, detail="An in-progress course can't have a grade yet")
    equivalent_id = None
    if data.get("equivalent_code"):
        if kind != "course":
            raise HTTPException(status_code=422, detail="Only a course can have a UMD equivalent")
        code = normalize_code(data["equivalent_code"])
        row = conn.execute("SELECT id FROM courses WHERE code = %s", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"UMD course {code} not found")
        equivalent_id = row["id"]
    return {
        "academic_term_id": data.get("academic_term_id"),
        "institution": institution,
        "kind": kind,
        "external_code": data.get("external_code"),
        "title": data.get("title"),
        "credits": data["credits"],
        "grade": data.get("grade"),
        "status": data.get("status") or "completed",
        "equivalent_course_id": equivalent_id,
        "verification": data.get("verification") or "student_reported",
        "verification_note": data.get("verification_note"),
    }


def requirement_options(conn, session: dict) -> list[dict]:
    program = find_program(conn, session["program_slug"])
    tree, _ = load_requirements(conn, program)
    options = []

    def visit(nodes, path):
        for node in nodes:
            if node["rule"] != "not_tracked":
                options.append({"key": node["key"], "name": node["name"], "path": path,
                                "category": node["category"]})
            visit(node["children"], path + [node["name"]])
    visit(tree, [])
    return options


def build_history(conn, session_id: UUID) -> dict:
    session = load_session(conn, session_id)
    check_terms(session)
    record = load_student_record(conn, session_id, session)
    current = session["current_term"] or today_term()

    transfers = conn.execute(
        """
        SELECT t.id, t.academic_term_id, t.institution, t.kind, t.external_code, t.title,
               t.credits, t.grade, t.status, c.code AS equivalent_code,
               c.name AS equivalent_name, t.verification, t.verification_note
        FROM transfer_credits t LEFT JOIN courses c ON c.id = t.equivalent_course_id
        WHERE t.session_id = %s ORDER BY t.id
        """,
        (session_id,)).fetchall()
    for t in transfers:
        t["counted"] = (t["status"] == "completed" and t["verification"] == "umd_verified"
                        and not (t["equivalent_code"]
                                 and record.completed.get(t["equivalent_code"], {}).get("source") == "umd"))

    terms = conn.execute(
        "SELECT id, term, institution, at_umd FROM academic_terms WHERE session_id = %s",
        (session_id,)).fetchall()
    terms.sort(key=lambda t: (ordinal(t["term"]), not t["at_umd"], t["institution"]))
    courses = [{k: c[k] for k in ("code", "name", "credits", "credits_min", "credits_max",
                                  "grade", "status", "academic_term_id")}
               for c in session["courses"]]
    out_terms = []
    for t in terms:
        period = ("past" if ordinal(t["term"]) < ordinal(current)
                  else "current" if t["term"] == current else "future")
        out_terms.append({
            **t, "period": period,
            "courses": [c for c in courses if c["academic_term_id"] == t["id"]],
            "transfers": [x for x in transfers if x["academic_term_id"] == t["id"]],
        })

    options = requirement_options(conn, session)
    names = {o["key"]: o["name"] for o in options}
    fulfillments = conn.execute(
        "SELECT id, requirement_key, method, verification, note, transfer_credit_id "
        "FROM requirement_fulfillments WHERE session_id = %s ORDER BY id",
        (session_id,)).fetchall()
    for f in fulfillments:
        f["requirement_name"] = names.get(f["requirement_key"], f["requirement_key"])
        f["counted"] = f["verification"] in COUNTED_VERIFICATIONS and f["requirement_key"] in names

    return {
        "current_term": current,
        "terms": out_terms,
        "unassigned_courses": [c for c in courses if c["academic_term_id"] is None],
        "unassigned_transfers": [x for x in transfers if x["academic_term_id"] is None],
        "fulfillments": fulfillments,
        "requirement_options": options,
        "summary": {"earned_credits": record.earned_credits,
                    "applicable_credits": record.applicable_credits,
                    "in_progress_credits": record.in_progress_credits,
                    "pending": record.pending},
    }

