"""Audit Log — FR-16. Read-only, Super Admin only."""
from fastapi import APIRouter, Depends

from app.db import get_conn
from app.deps import require_role

router = APIRouter(prefix="/api/audit", tags=["audit"])

MAX_LIMIT = 2000
MIN_LIMIT = 1


@router.get("")
def list_audit_log(module: str = None, date_from: str = None, date_to: str = None,
                    limit: int = 500, session: dict = Depends(require_role("super_admin"))):
    safe_limit = max(MIN_LIMIT, min(limit, MAX_LIMIT))

    conn = get_conn()
    try:
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if module:
            sql += " AND module=?"
            params.append(module)
        if date_from:
            sql += " AND date>=?"
            params.append(date_from)
        if date_to:
            sql += " AND date<=?"
            params.append(date_to)

        # Sorting works correctly here because date/time are always stored
        # in YYYY-MM-DD / HH:MM:SS format, which sorts correctly as plain
        # text. If that storage format ever changes, this ordering breaks.
        sql += " ORDER BY date DESC, time DESC LIMIT ?"
        params.append(safe_limit)

        rows = conn.execute(sql, params).fetchall()
        return {"logs": [dict(r) for r in rows], "limit_applied": safe_limit}
    finally:
        conn.close()