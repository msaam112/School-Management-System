"""Parent Management — FR-5."""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/parents", tags=["parents"])

MIN_CNIC_LENGTH = 5  # deliberately loose — supports non-Pakistani ID formats too


def normalize_cnic(cnic: str) -> str:
    """Keeps only alphanumeric characters, lowercased, so formatting
    differences (dashes, spaces, case) never cause a mismatch — this must
    stay consistent with the normalization used in auth.py's parent login."""
    return re.sub(r"[^0-9a-zA-Z]", "", cnic or "").lower()


class ParentCreate(BaseModel):
    name: str
    cnic: str
    phone: Optional[str] = None
    address: Optional[str] = None


class ParentUpdate(BaseModel):
    name: Optional[str] = None
    cnic: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


@router.get("")
def list_parents(session: dict = Depends(require_role("super_admin", "principal"))):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM parents ORDER BY name").fetchall()
        return {"parents": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_parent(body: ParentCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    cnic_raw = body.cnic.strip()
    if not name or not cnic_raw:
        return json_err("Name and CNIC are required", 400)

    normalized = normalize_cnic(cnic_raw)
    if len(normalized) < MIN_CNIC_LENGTH:
        return json_err(f"CNIC must be at least {MIN_CNIC_LENGTH} characters", 400)

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM parents WHERE cnic=? OR REPLACE(REPLACE(LOWER(cnic),'-',''),' ','')=?",
            (cnic_raw, normalized)).fetchone()
        if existing:
            return json_err("A parent with this CNIC already exists", 400)

        pid = new_id("par")
        conn.execute("INSERT INTO parents (id, name, cnic, phone, address) VALUES (?,?,?,?,?)",
                     (pid, name, cnic_raw, body.phone, body.address))
        audit(session, "Parents", "Create", f"Added parent {name}", conn=conn)
        conn.commit()
        return {"id": pid}
    finally:
        conn.close()


@router.put("/{pid}")
def update_parent(pid: str, body: ParentUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM parents WHERE id=?", (pid,)).fetchone()
        if not existing:
            return json_err("Parent not found", 404)

        if body.cnic is not None:
            cnic_raw = body.cnic.strip()
            normalized = normalize_cnic(cnic_raw)
            if len(normalized) < MIN_CNIC_LENGTH:
                return json_err(f"CNIC must be at least {MIN_CNIC_LENGTH} characters", 400)

            dup = conn.execute(
                "SELECT id FROM parents WHERE (cnic=? OR REPLACE(REPLACE(LOWER(cnic),'-',''),' ','')=?) AND id!=?",
                (cnic_raw, normalized, pid)).fetchone()
            if dup:
                return json_err("Another parent already uses this CNIC", 400)

        sets, params = [], []
        for f in ["name", "cnic", "phone", "address"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v.strip() if f in ("name", "cnic") and isinstance(v, str) else v)
        if sets:
            conn.execute("UPDATE parents SET " + ", ".join(sets) + " WHERE id=?", params + [pid])
            audit(session, "Parents", "Update", f"Updated parent {pid}", conn=conn)
            conn.commit()
        return {"message": "Parent updated"}
    finally:
        conn.close()


@router.delete("/{pid}")
def delete_parent(pid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM parents WHERE id=?", (pid,)).fetchone()
        if not existing:
            return json_err("Parent not found", 404)

        linked = conn.execute("SELECT COUNT(*) c FROM students WHERE parent_id=?", (pid,)).fetchone()["c"]
        if linked:
            return json_err("Cannot delete a parent linked to students", 400)

        conn.execute("DELETE FROM parents WHERE id=?", (pid,))
        audit(session, "Parents", "Delete", f"Removed parent {pid}", conn=conn)
        conn.commit()
        return {"message": "Parent removed"}
    finally:
        conn.close()