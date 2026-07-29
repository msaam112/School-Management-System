"""Subject Management — FR-8."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/subjects", tags=["subjects"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge")


class SubjectCreate(BaseModel):
    name: str


class SubjectUpdate(BaseModel):
    name: Optional[str] = None


@router.get("")
def list_subjects(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        return {"subjects": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_subject(body: SubjectCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    if not name:
        return json_err("Subject name is required", 400)

    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM subjects WHERE name=?", (name,)).fetchone()
        if existing:
            return json_err("This subject already exists", 400)

        sid = new_id("sub")
        conn.execute("INSERT INTO subjects (id, name) VALUES (?,?)", (sid, name))
        audit(session, "Subjects", "Create", f"Added subject {name}", conn=conn)
        conn.commit()
        return {"id": sid}
    finally:
        conn.close()


@router.put("/{sid}")
def update_subject(sid: str, body: SubjectUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM subjects WHERE id=?", (sid,)).fetchone()
        if not existing:
            return json_err("Subject not found", 404)
        if body.name:
            conn.execute("UPDATE subjects SET name=? WHERE id=?", (body.name.strip(), sid))
            audit(session, "Subjects", "Update", f"Updated subject {sid}", conn=conn)
            conn.commit()
        return {"message": "Subject updated"}
    finally:
        conn.close()


@router.delete("/{sid}")
def delete_subject(sid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM subjects WHERE id=?", (sid,)).fetchone()
        if not existing:
            return json_err("Subject not found", 404)

        in_use = conn.execute(
            "SELECT COUNT(*) c FROM teacher_assignments WHERE subject_id=?", (sid,)).fetchone()["c"]
        if in_use:
            return json_err("Cannot delete a subject that is assigned to teachers", 400)

        conn.execute("DELETE FROM subjects WHERE id=?", (sid,))
        audit(session, "Subjects", "Delete", f"Removed subject {sid}", conn=conn)
        conn.commit()
        return {"message": "Subject removed"}
    finally:
        conn.close()