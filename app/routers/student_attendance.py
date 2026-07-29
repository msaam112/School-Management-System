"""Student Attendance — FR-9, UC-4.

Business rules enforced here:
- Only Class Incharge may mark/submit (Super Admin & Principal are VIEW ONLY).
- A Class Incharge may only touch their OWN assigned class.
- Once locked, no further writes are accepted until a Super Admin unlocks it.
- Attendance is unique per student per day (DB-level UNIQUE constraint backs this up).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.config import ATTENDANCE_STATUSES
from app.db import get_conn, now_iso, today
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/attendance/student", tags=["student_attendance"])

VIEW_ROLES = ("super_admin", "principal", "class_incharge", "parent")


class AttendanceRecord(BaseModel):
    student_id: str
    status: str


class AttendanceSubmit(BaseModel):
    class_id: str
    section_id: Optional[str] = None
    date: Optional[str] = None
    records: List[AttendanceRecord]
    submit: bool = False


def _class_incharge_class_id(conn, uid: str):
    t = conn.execute("SELECT class_id FROM teachers WHERE user_id=? AND is_class_incharge=1", (uid,)).fetchone()
    return t["class_id"] if t else None


@router.get("")
def get_attendance(class_id: str = None, section_id: str = None, date: str = None,
                    session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        d = date or today()
        role = session["role"]

        if role == "parent":
            sid = session.get("student_id")
            rows = conn.execute(
                "SELECT s.id, s.roll_number, s.name, sa.status, sa.locked FROM students s "
                "LEFT JOIN student_attendance sa ON sa.student_id=s.id AND sa.date=? WHERE s.id=?",
                (d, sid)).fetchall()
            return {"students": [dict(r) for r in rows], "date": d}

        if role == "class_incharge":
            own_class = _class_incharge_class_id(conn, session["uid"])
            if not own_class:
                return json_err("You are not assigned as a Class Incharge for any class", 403)
            if class_id and class_id != own_class:
                return json_err("You may only manage your assigned class", 403)
            class_id = own_class

        if not class_id:
            return json_err("class_id is required", 400)

        sql = ("SELECT s.id, s.roll_number, s.name, sa.status, sa.locked FROM students s "
               "LEFT JOIN student_attendance sa ON sa.student_id=s.id AND sa.date=? "
               "WHERE s.class_id=?" + (" AND s.section_id=?" if section_id else "") +
               " ORDER BY s.roll_number")
        params = (d, class_id) + ((section_id,) if section_id else ())
        rows = conn.execute(sql, params).fetchall()

        locked_count = conn.execute(
            "SELECT COUNT(*) c FROM student_attendance sa JOIN students s ON sa.student_id=s.id "
            "WHERE sa.date=? AND sa.locked=1 AND s.class_id=?" + (" AND s.section_id=?" if section_id else ""),
            params).fetchone()["c"]

        return {"students": [dict(r) for r in rows], "date": d, "class_id": class_id,
                "section_id": section_id, "locked": locked_count > 0}
    finally:
        conn.close()


@router.post("")
def submit_attendance(body: AttendanceSubmit, session: dict = Depends(require_role("class_incharge"))):
    conn = get_conn()
    try:
        own_class = _class_incharge_class_id(conn, session["uid"])
        if not own_class:
            return json_err("You are not assigned as a Class Incharge for any class", 403)
        if body.class_id != own_class:
            return json_err("You may only manage your assigned class", 403)

        d = body.date or today()

        # BR-7: reject writes to already-locked records instead of silently overwriting.
        already_locked = conn.execute(
            "SELECT COUNT(*) c FROM student_attendance sa JOIN students s ON sa.student_id=s.id "
            "WHERE sa.date=? AND sa.locked=1 AND s.class_id=?", (d, own_class)).fetchone()["c"]
        if already_locked:
            return json_err("Attendance for this date is locked. Ask a Super Admin to unlock it first.", 400)

        for rec in body.records:
            if rec.status not in ATTENDANCE_STATUSES:
                continue
            conn.execute(
                "INSERT INTO student_attendance (id, student_id, date, status, locked, submitted_at, submitted_by) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(student_id, date) DO UPDATE SET status=excluded.status, locked=excluded.locked, "
                "submitted_at=excluded.submitted_at, submitted_by=excluded.submitted_by",
                (new_id("att"), rec.student_id, d, rec.status, 1 if body.submit else 0,
                 now_iso() if body.submit else None, session.get("uid") if body.submit else None))

        audit(session, "Attendance", "Submit" if body.submit else "Draft",
              f"{'Submitted' if body.submit else 'Saved draft'} student attendance for {d}, class {own_class}",
              conn=conn)
        conn.commit()
        return {"message": "Attendance saved", "locked": body.submit}
    finally:
        conn.close()