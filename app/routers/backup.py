"""Database Backup — FR-17, UC-8. Super Admin only."""
import json
import datetime
from fastapi import APIRouter, Depends, Response

from app.db import get_conn
from app.helpers import audit
from app.deps import require_role

router = APIRouter(prefix="/api/backup", tags=["backup"])

# Every table listed in the SRS §6.2/§6.4 that should be included in a full backup.
BACKUP_TABLES = [
    "school", "users", "teachers", "parents", "classes", "sections", "subjects",
    "teacher_assignments", "students", "student_attendance", "teacher_attendance",
    "attendance_unlocks", "examinations", "results", "fee_structures", "fee_challans",
    "manual_fees", "promotions", "audit_log", "settings",
]


@router.post("")
def create_backup(session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        dump = {}
        for table in BACKUP_TABLES:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            dump[table] = [dict(r) for r in rows]

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sms_backup_{ts}.json"

        audit(session, "Backup", "Create", f"Database backup {filename} created", conn=conn)
        conn.commit()

        payload = json.dumps(dump, indent=2, default=str).encode("utf-8")
        return Response(content=payload, media_type="application/json",
                         headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    finally:
        conn.close()