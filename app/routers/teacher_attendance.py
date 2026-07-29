"""Teacher Attendance — FR-10, UC-5.

Business rules enforced here:
- Principal marks it normally.
- Super Admin may submit ONLY if it hasn't been submitted yet for that date
  (i.e. it's currently unlocked) — once locked, Super Admin is view/report only
  until a Super Admin unlock event happens.
- Teacher role sees only their OWN attendance record.
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

router = APIRouter(prefix="/api/attendance/teacher", tags=["teacher_attendance"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge")
SUBMIT_ROLES = ("principal", "super_admin")


class TeacherAttendanceRecord(BaseModel):
    teacher_id: str
    status: str


class TeacherAttendanceSubmit(BaseModel):
    date: Optional[str] = None
    records: List[TeacherAttendanceRecord]
    submit: bool = False


@router.get("")
def get_teacher_attendance(date: str = None, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        d = date or today()
        role = session["role"]

        if role == "teacher":
            t = conn.execute("SELECT id FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
            if not t:
                return {"teachers": [], "date": d, "locked": False}
            row = conn.execute(
                "SELECT t.id, t.employee_id, t.name, ta.status, ta.locked FROM teachers t "
                "LEFT JOIN teacher_attendance ta ON ta.teacher_id=t.id AND ta.date=? WHERE t.id=?",
                (d, t["id"])).fetchone()
            return {"teachers": [dict(row)] if row else [], "date": d}

        rows = conn.execute(
            "SELECT t.id, t.employee_id, t.name, ta.status, ta.locked FROM teachers t "
            "LEFT JOIN teacher_attendance ta ON ta.teacher_id=t.id AND ta.date=? ORDER BY t.name",
            (d,)).fetchall()
        locked = conn.execute(
            "SELECT COUNT(*) c FROM teacher_attendance WHERE date=? AND locked=1", (d,)).fetchone()["c"]
        return {"teachers": [dict(r) for r in rows], "date": d, "locked": locked > 0}
    finally:
        conn.close()


@router.post("")
def submit_teacher_attendance(body: TeacherAttendanceSubmit,
                               session: dict = Depends(require_role(*SUBMIT_ROLES))):
    conn = get_conn()
    try:
        d = body.date or today()

        # BR-9 + BR-7 combined: once ANY record for this date is locked, nobody
        # (Principal or Super Admin) may submit again until a Super Admin unlocks it.
        already_locked = conn.execute(
            "SELECT COUNT(*) c FROM teacher_attendance WHERE date=? AND locked=1", (d,)).fetchone()["c"]
        if already_locked:
            return json_err("Teacher attendance for this date is locked. Ask a Super Admin to unlock it first.", 400)

        for rec in body.records:
            if rec.status not in ATTENDANCE_STATUSES:
                continue
            conn.execute(
                "INSERT INTO teacher_attendance (id, teacher_id, date, status, locked, submitted_at, submitted_by) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(teacher_id, date) DO UPDATE SET status=excluded.status, locked=excluded.locked, "
                "submitted_at=excluded.submitted_at, submitted_by=excluded.submitted_by",
                (new_id("tat"), rec.teacher_id, d, rec.status, 1 if body.submit else 0,
                 now_iso() if body.submit else None, session.get("uid") if body.submit else None))

        audit(session, "Teacher Attendance", "Submit" if body.submit else "Draft",
              f"{'Submitted' if body.submit else 'Saved draft'} teacher attendance for {d} by {session['role']}",
              conn=conn)
        conn.commit()
        return {"message": "Teacher attendance saved", "locked": body.submit}
    finally:
        conn.close()