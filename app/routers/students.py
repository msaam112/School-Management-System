"""Student Management — FR-4, UC-2."""
import sqlite3
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn, today
from app.security import new_id
from app.helpers import audit
from app.deps import require_session, require_role
from app.main import json_err
from app.routers.parents import normalize_cnic

router = APIRouter(prefix="/api/students", tags=["students"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge", "parent")
SEARCH_RESULT_LIMIT = 200


class StudentCreate(BaseModel):
    name: str
    roll_number: str
    admission_id: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    admission_date: Optional[str] = None
    status: Optional[str] = "active"
    class_id: str
    section_id: str
    # either provide parent_id, or the parent_* fields to create/link a new one
    parent_id: Optional[str] = None
    parent_name: Optional[str] = None
    parent_cnic: Optional[str] = None
    parent_phone: Optional[str] = None
    parent_address: Optional[str] = None


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    roll_number: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    admission_date: Optional[str] = None
    status: Optional[str] = None
    class_id: Optional[str] = None
    section_id: Optional[str] = None


def _accessible_filter(session: dict, conn):
    """Returns (where_clause, params) restricting rows to what this role may see."""
    role = session["role"]
    if role in ("super_admin", "principal"):
        return "1=1", ()
    if role == "class_incharge":
        t = conn.execute("SELECT class_id FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
        return ("s.class_id=?", (t["class_id"],)) if t and t["class_id"] else ("0=1", ())
    if role == "teacher":
        t = conn.execute("SELECT id FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
        return ("s.class_id IN (SELECT class_id FROM teacher_assignments WHERE teacher_id=?)",
                (t["id"],)) if t else ("0=1", ())
    if role == "parent":
        return "s.id=?", (session.get("student_id"),)
    return "0=1", ()


def _section_belongs_to_class(conn, section_id: str, class_id: str) -> bool:
    row = conn.execute("SELECT id FROM sections WHERE id=? AND class_id=?", (section_id, class_id)).fetchone()
    return row is not None


@router.get("")
def list_students(request: Request, class_id: str = None, section_id: str = None,
                   session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        flt, params = _accessible_filter(session, conn)
        sql = ("SELECT s.*, c.name class_name, sec.name section_name, p.name parent_name FROM students s "
               "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
               "LEFT JOIN parents p ON s.parent_id=p.id WHERE " + flt)
        params = list(params)
        if class_id:
            sql += " AND s.class_id=?"; params.append(class_id)
        if section_id:
            sql += " AND s.section_id=?"; params.append(section_id)
        sql += " ORDER BY s.roll_number"
        rows = conn.execute(sql, params).fetchall()
        return {"students": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@router.get("/search")
def search_students(q: str = "", session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        flt, params = _accessible_filter(session, conn)
        like = f"%{q.strip()}%"
        sql = ("SELECT s.*, c.name class_name, sec.name section_name FROM students s "
               "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
               "WHERE " + flt + " AND (s.name LIKE ? OR s.roll_number LIKE ? OR s.admission_id LIKE ?) "
               "ORDER BY s.roll_number LIMIT ?")
        rows = conn.execute(sql, list(params) + [like, like, like, SEARCH_RESULT_LIMIT]).fetchall()
        return {"students": [dict(r) for r in rows], "truncated": len(rows) == SEARCH_RESULT_LIMIT}
    finally:
        conn.close()


@router.get("/{sid}")
def get_student(sid: str, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT s.*, c.name class_name, sec.name section_name, p.name parent_name, "
            "p.cnic parent_cnic, p.phone parent_phone FROM students s "
            "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
            "LEFT JOIN parents p ON s.parent_id=p.id WHERE s.id=?", (sid,)).fetchone()
        if not row:
            return json_err("Student not found", 404)
        if session["role"] == "parent" and session.get("student_id") != sid:
            return json_err("Access denied", 403)
        return {"student": dict(row)}
    finally:
        conn.close()


@router.post("")
def create_student(body: StudentCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    roll = body.roll_number.strip()
    if not name or not roll:
        return json_err("Student name and roll number are required", 400)

    conn = get_conn()
    try:
        dup_roll = conn.execute("SELECT id FROM students WHERE roll_number=?", (roll,)).fetchone()
        if dup_roll:
            return json_err("Roll number already in use", 400)

        if not _section_belongs_to_class(conn, body.section_id, body.class_id):
            return json_err("Selected section does not belong to the selected class", 400)

        # Resolve parent: existing id, or create/link by CNIC (normalized,
        # matching parents.py, so formatting differences don't create duplicates)
        parent_id = body.parent_id
        if not parent_id:
            if not body.parent_name or not body.parent_cnic:
                return json_err("Parent name and CNIC are required", 400)

            cnic_raw = body.parent_cnic.strip()
            normalized = normalize_cnic(cnic_raw)
            existing = conn.execute(
                "SELECT id FROM parents WHERE cnic=? OR REPLACE(REPLACE(LOWER(cnic),'-',''),' ','')=?",
                (cnic_raw, normalized)).fetchone()
            if existing:
                parent_id = existing["id"]
            else:
                parent_id = new_id("par")
                conn.execute("INSERT INTO parents (id, name, cnic, phone, address) VALUES (?,?,?,?,?)",
                             (parent_id, body.parent_name.strip(), cnic_raw,
                              body.parent_phone, body.parent_address))

        sid = new_id("stu")
        admission_id = body.admission_id or f"ADM-{roll}"

        try:
            conn.execute(
                "INSERT INTO students (id, admission_id, roll_number, name, gender, dob, admission_date, "
                "status, class_id, section_id, parent_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sid, admission_id, roll, name, body.gender, body.dob,
                 body.admission_date or today(), body.status or "active",
                 body.class_id, body.section_id, parent_id))
        except sqlite3.IntegrityError:
            conn.rollback()
            return json_err(f"Admission ID '{admission_id}' is already in use. Please specify a different one.", 400)

        audit(session, "Students", "Create", f"Registered student {name} (Roll {roll})", conn=conn)
        conn.commit()
        return {"id": sid, "message": "Student registered"}
    finally:
        conn.close()


@router.put("/{sid}")
def update_student(sid: str, body: StudentUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if not existing:
            return json_err("Student not found", 404)

        # If either class_id or section_id is changing, validate the resulting
        # combination is consistent (the section actually belongs to the class).
        new_class_id = body.class_id if body.class_id is not None else existing["class_id"]
        new_section_id = body.section_id if body.section_id is not None else existing["section_id"]
        if (body.class_id is not None or body.section_id is not None):
            if not _section_belongs_to_class(conn, new_section_id, new_class_id):
                return json_err("Selected section does not belong to the selected class", 400)

        if body.roll_number is not None:
            dup = conn.execute("SELECT id FROM students WHERE roll_number=? AND id!=?",
                                (body.roll_number.strip(), sid)).fetchone()
            if dup:
                return json_err("Roll number already in use", 400)

        sets, params = [], []
        for f in ["name", "roll_number", "gender", "dob", "admission_date", "status", "class_id", "section_id"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v)
        if sets:
            conn.execute("UPDATE students SET " + ", ".join(sets) + " WHERE id=?", params + [sid])
            audit(session, "Students", "Update", f"Updated student {sid}", conn=conn)
            conn.commit()
        return {"message": "Student updated"}
    finally:
        conn.close()


@router.delete("/{sid}")
def delete_student(sid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if not existing:
            return json_err("Student not found", 404)

        # Block deletion if the student has real academic/financial history —
        # deleting that history silently would be a serious, irreversible
        # data-loss decision that shouldn't happen as a side effect of a
        # simple "remove student" click.
        counts = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM student_attendance WHERE student_id=:sid) AS attendance,
                (SELECT COUNT(*) FROM results WHERE student_id=:sid) AS results,
                (SELECT COUNT(*) FROM fee_challans WHERE student_id=:sid) AS fees,
                (SELECT COUNT(*) FROM promotions WHERE student_id=:sid) AS promotions
        """, {"sid": sid}).fetchone()

        history_parts = []
        if counts["attendance"]: history_parts.append(f"{counts['attendance']} attendance record(s)")
        if counts["results"]: history_parts.append(f"{counts['results']} exam result(s)")
        if counts["fees"]: history_parts.append(f"{counts['fees']} fee challan(s)")
        if counts["promotions"]: history_parts.append(f"{counts['promotions']} promotion record(s)")

        if history_parts:
            return json_err(
                "Cannot delete this student — they have " + ", ".join(history_parts) +
                ". Consider setting their status to 'inactive' instead of deleting.",
                400
            )

        conn.execute("DELETE FROM students WHERE id=?", (sid,))
        audit(session, "Students", "Delete", f"Removed student {sid}", conn=conn)
        conn.commit()
        return {"message": "Student removed"}
    finally:
        conn.close()