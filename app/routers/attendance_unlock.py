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


@router.post("/unlock")
def unlock_attendance(body: UnlockRequest, session: dict = Depends(require_role("super_admin"))):
    reason = body.reason.strip()
    if not reason:
        return json_err("A reason is mandatory to unlock attendance", 400)

    if body.type not in ("student", "teacher"):
        return json_err("Invalid attendance type", 400)

    conn = get_conn()
    try:
        if body.type == "student":
            if not body.class_id:
                return json_err("class_id is required to unlock student attendance", 400)
            sql = ("UPDATE student_attendance SET locked=0 WHERE date=? AND locked=1 AND student_id IN "
                   "(SELECT id FROM students WHERE class_id=?" +
                   (" AND section_id=?" if body.section_id else "") + ")")
            params = (body.date, body.class_id) + ((body.section_id,) if body.section_id else ())
            conn.execute(sql, params)
        else:
            conn.execute("UPDATE teacher_attendance SET locked=0 WHERE date=? AND locked=1", (body.date,))

        now = datetime.datetime.now()
        conn.execute(
            "INSERT INTO attendance_unlocks (id, attendance_type, ref_date, class_id, section_id, "
            "reason, unlocked_by, unlock_date, unlock_time) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("unl"), body.type, body.date, body.class_id, body.section_id, reason,
             session["uid"], now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")))

        audit(session, "Attendance", "Unlock",
              f"Unlocked {body.type} attendance for {body.date}: {reason}", conn=conn)
        conn.commit()
        return {"message": "Attendance unlocked"}
    finally:
        conn.close()