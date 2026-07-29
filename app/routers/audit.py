"""Audit Log — FR-16. Read-only, Super Admin only."""
from fastapi import APIRouter, Depends

from app.db import get_conn
from app.deps import require_role

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_log(module: str = None, limit: int = 500,
                    session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        sql = "SELECT * FROM audit_log"
        params = []
        if module:
            sql += " WHERE module=?"
            params.append(module)
        sql += " ORDER BY date DESC, time DESC LIMIT ?"
        params.append(min(limit, 2000))
        rows = conn.execute(sql, params).fetchall()
        return {"logs": [dict(r) for r in rows]}
    finally:
        conn.close()