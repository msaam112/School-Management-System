"""Fee Structure Management — FR-14.1."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/fee-structures", tags=["fee_structures"])

VIEW_ROLES = ("super_admin", "principal")


class FeeStructureCreate(BaseModel):
    class_id: str
    admission_fee: Optional[float] = 0
    tuition_fee: Optional[float] = 0
    exam_fee: Optional[float] = 0
    custom_name: Optional[str] = None
    custom_fee: Optional[float] = 0


class FeeStructureUpdate(BaseModel):
    admission_fee: Optional[float] = None
    tuition_fee: Optional[float] = None
    exam_fee: Optional[float] = None
    custom_name: Optional[str] = None
    custom_fee: Optional[float] = None


@router.get("")
def list_fee_structures(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT fs.*, c.name class_name FROM fee_structures fs "
            "JOIN classes c ON fs.class_id=c.id ORDER BY c.name").fetchall()
        return {"structures": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_fee_structure(body: FeeStructureCreate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        cls = conn.execute("SELECT id FROM classes WHERE id=?", (body.class_id,)).fetchone()
        if not cls:
            return json_err("Class not found", 404)

        existing = conn.execute("SELECT id FROM fee_structures WHERE class_id=?", (body.class_id,)).fetchone()
        if existing:
            return json_err("A fee structure already exists for this class. Edit it instead.", 400)

        fsid = new_id("fs")
        conn.execute(
            "INSERT INTO fee_structures (id, class_id, admission_fee, tuition_fee, exam_fee, "
            "custom_name, custom_fee) VALUES (?,?,?,?,?,?,?)",
            (fsid, body.class_id, body.admission_fee or 0, body.tuition_fee or 0,
             body.exam_fee or 0, body.custom_name, body.custom_fee or 0))
        audit(session, "Fees", "Structure", f"Created fee structure for class {body.class_id}", conn=conn)
        conn.commit()
        return {"id": fsid}
    finally:
        conn.close()


@router.put("/{fsid}")
def update_fee_structure(fsid: str, body: FeeStructureUpdate,
                          session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fee_structures WHERE id=?", (fsid,)).fetchone()
        if not existing:
            return json_err("Fee structure not found", 404)

        sets, params = [], []
        for f in ["admission_fee", "tuition_fee", "exam_fee", "custom_name", "custom_fee"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v)
        if sets:
            conn.execute("UPDATE fee_structures SET " + ", ".join(sets) + " WHERE id=?", params + [fsid])
            audit(session, "Fees", "Structure", f"Updated fee structure {fsid}", conn=conn)
            conn.commit()
        return {"message": "Fee structure updated"}
    finally:
        conn.close()


@router.delete("/{fsid}")
def delete_fee_structure(fsid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fee_structures WHERE id=?", (fsid,)).fetchone()
        if not existing:
            return json_err("Fee structure not found", 404)
        conn.execute("DELETE FROM fee_structures WHERE id=?", (fsid,))
        audit(session, "Fees", "Structure Delete", f"Removed fee structure {fsid}", conn=conn)
        conn.commit()
        return {"message": "Fee structure removed"}
    finally:
        conn.close()