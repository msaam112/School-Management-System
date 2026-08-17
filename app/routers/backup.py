"""Database Backup — FR-17, UC-8. Super Admin only."""
import json
import datetime
from fastapi import APIRouter, Depends, Response

from app.db import get_conn
from app.helpers import audit
from app.deps import require_role

router = APIRouter(prefix="/api/backup", tags=["backup"])

# Every table that should be included in a full backup (SRS §6.2/§6.4).
BACKUP_TABLES = [
    "school", "users", "teachers", "principals", "parents", "classes", "sections", "subjects",
    "teacher_assignments", "students", "student_attendance", "teacher_attendance",
    "attendance_unlocks", "examinations", "results", "fee_structures", "fee_challans",
    "manual_fees", "promotions", "audit_log", "settings",
]

# Columns that are genuinely sensitive and excluded from normal backups.
# password_hash is a bcrypt hash, not plaintext, but a downloadable backup
# file is a much easier target to exfiltrate than the live login endpoint
# (which is rate-limited) — so it's deliberately left out by default.
SENSITIVE_COLUMNS = {"users": ["password_hash"]}

BACKUP_SCHEMA_VERSION = "1.1"


@router.post("")
def create_backup(include_password_hashes: bool = False,
                   session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        dump = {
            "_meta": {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "generated_at": datetime.datetime.now().isoformat(),
                "generated_by": session.get("name") or session.get("uid"),
                "password_hashes_included": include_password_hashes,
            }
        }
        failed_tables = []

        for table in BACKUP_TABLES:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                table_dump = []
                sensitive_cols = SENSITIVE_COLUMNS.get(table, []) if not include_password_hashes else []
                for r in rows:
                    row_dict = dict(r)
                    for col in sensitive_cols:
                        if col in row_dict:
                            row_dict[col] = "[omitted from backup — see include_password_hashes]"
                    table_dump.append(row_dict)
                dump[table] = table_dump
            except Exception as e:
                failed_tables.append(table)
                dump[table] = None

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sms_backup_{ts}.json"

        note = f" ({len(failed_tables)} table(s) failed: {', '.join(failed_tables)})" if failed_tables else ""
        audit(session, "Backup", "Create", f"Database backup {filename} created{note}", conn=conn)
        conn.commit()

        payload = json.dumps(dump, indent=2, default=str).encode("utf-8")
        return Response(content=payload, media_type="application/json",
                         headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    finally:
        conn.close()