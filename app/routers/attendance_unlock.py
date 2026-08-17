"""Attendance Unlock — FR-9.3, BR-8.

Only Super Admin may unlock. Reason is mandatory. Date, Time, and User
are captured as distinct fields (not a single combined timestamp).
"""
import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/attendance", tags=["attendance_unlock"])


class UnlockRequest(BaseModel):
    type: str  # "student" | "teacher"
    date: str
    reason: str
    class_id: Optional[str] = None
    section_id: Optional[str] = None


def _is_valid_date(value: str) -> bool:
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


@router.post("/unlock")
def unlock_attendance(body: UnlockRequest, session: dict = Depends(require_role("super_admin"))):
    reason = body.reason.strip()
    if not reason:
        return json_err("A reason is mandatory to unlock attendance", 400)

    if body.type not in ("student", "teacher"):
        return json_err("Invalid attendance type", 400)

    if not _is_valid_date(body.date):
        return json_err("Date must be in YYYY-MM-DD format", 400)

    conn = get_conn()
    try:
        if body.type == "student":
            if not body.class_id:
                return json_err("class_id is required to unlock student attendance", 400)

            cls = conn.execute("SELECT id FROM classes WHERE id=?", (body.class_id,)).fetchone()
            if not cls:
                return json_err("Class not found", 404)

            if body.section_id:
                sec = conn.execute("SELECT id FROM sections WHERE id=? AND class_id=?",
                                    (body.section_id, body.class_id)).fetchone()
                if not sec:
                    return json_err("Selected section does not belong to the selected class", 400)

            sql = ("UPDATE student_attendance SET locked=0 WHERE date=? AND locked=1 AND student_id IN "
                   "(SELECT id FROM students WHERE class_id=?" +
                   (" AND section_id=?" if body.section_id else "") + ")")
            params = (body.date, body.class_id) + ((body.section_id,) if body.section_id else ())
            cursor = conn.execute(sql, params)
        else:
            cursor = conn.execute("UPDATE teacher_attendance SET locked=0 WHERE date=? AND locked=1", (body.date,))

        # If nothing was actually locked/unlocked, don't claim success or
        # write a misleading audit trail entry for an action that didn't
        # actually happen — this is the exact gap that produced a confusing
        # "0 rows affected but still says success" result during earlier testing.
        if cursor.rowcount == 0:
            conn.rollback()
            return json_err(
                "Nothing was unlocked. There may be no locked attendance for this date/class, "
                "or the date/class combination doesn't match any existing records.",
                404
            )

        now = datetime.datetime.now()
        conn.execute(
            "INSERT INTO attendance_unlocks (id, attendance_type, ref_date, class_id, section_id, "
            "reason, unlocked_by, unlock_date, unlock_time) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("unl"), body.type, body.date, body.class_id, body.section_id, reason,
             session["uid"], now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")))

        audit(session, "Attendance", "Unlock",
              f"Unlocked {body.type} attendance for {body.date}: {reason} ({cursor.rowcount} record(s) affected)",
              conn=conn)
        conn.commit()
        return {"message": "Attendance unlocked", "records_affected": cursor.rowcount}
    finally:
        conn.close()