"""Class & Section Management — FR-7."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.config import MAX_SECTIONS_PER_CLASS
from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api", tags=["classes"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge")


class ClassCreate(BaseModel):
    name: str


class ClassUpdate(BaseModel):
    name: Optional[str] = None


class SectionCreate(BaseModel):
    class_id: str
    name: str


# ------------------------------------------------------------------ classes
@router.get("/classes")
def list_classes(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM sections WHERE class_id=c.id) sections, "
            "(SELECT COUNT(*) FROM students WHERE class_id=c.id) students "
            "FROM classes c ORDER BY c.name").fetchall()
        return {"classes": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/classes")
def create_class(body: ClassCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    if not name:
        return json_err("Class name is required", 400)

    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM classes WHERE name=?", (name,)).fetchone()
        if existing:
            return json_err("A class with this name already exists", 400)

        cid = new_id("cls")
        conn.execute("INSERT INTO classes (id, name) VALUES (?,?)", (cid, name))
        audit(session, "Classes", "Create", f"Added class {name}", conn=conn)
        conn.commit()
        return {"id": cid}
    finally:
        conn.close()


@router.put("/classes/{cid}")
def update_class(cid: str, body: ClassUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM classes WHERE id=?", (cid,)).fetchone()
        if not existing:
            return json_err("Class not found", 404)
        if body.name:
            conn.execute("UPDATE classes SET name=? WHERE id=?", (body.name.strip(), cid))
            audit(session, "Classes", "Update", f"Renamed class {cid}", conn=conn)
            conn.commit()
        return {"message": "Class updated"}
    finally:
        conn.close()


@router.delete("/classes/{cid}")
def delete_class(cid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM classes WHERE id=?", (cid,)).fetchone()
        if not existing:
            return json_err("Class not found", 404)

        students = conn.execute("SELECT COUNT(*) c FROM students WHERE class_id=?", (cid,)).fetchone()["c"]
        if students:
            return json_err("Cannot delete a class with enrolled students", 400)

        refs = conn.execute(
            "SELECT (SELECT COUNT(*) FROM teacher_assignments WHERE class_id=?) "
            "+ (SELECT COUNT(*) FROM fee_structures WHERE class_id=?) "
            "+ (SELECT COUNT(*) FROM examinations WHERE class_id=?) AS c",
            (cid, cid, cid)).fetchone()["c"]
        if refs:
            return json_err("Cannot delete a class with assignments, fee structures, or exams", 400)

        conn.execute("DELETE FROM sections WHERE class_id=?", (cid,))
        conn.execute("DELETE FROM classes WHERE id=?", (cid,))
        audit(session, "Classes", "Delete", f"Removed class {cid}", conn=conn)
        conn.commit()
        return {"message": "Class removed"}
    finally:
        conn.close()


# ------------------------------------------------------------------ sections
@router.get("/sections")
def list_sections(class_id: str = None, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        sql = "SELECT s.*, c.name class_name FROM sections s JOIN classes c ON s.class_id=c.id"
        params = ()
        if class_id:
            sql += " WHERE s.class_id=?"
            params = (class_id,)
        rows = conn.execute(sql + " ORDER BY c.name, s.name", params).fetchall()
        return {"sections": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/sections")
def create_section(body: SectionCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    if not body.class_id or not name:
        return json_err("Class and section name are required", 400)

    conn = get_conn()
    try:
        cls = conn.execute("SELECT id FROM classes WHERE id=?", (body.class_id,)).fetchone()
        if not cls:
            return json_err("Class not found", 404)

        count = conn.execute(
            "SELECT COUNT(*) c FROM sections WHERE class_id=?", (body.class_id,)).fetchone()["c"]
        if count >= MAX_SECTIONS_PER_CLASS:
            return json_err(f"Maximum {MAX_SECTIONS_PER_CLASS} sections per class allowed", 400)

        dup = conn.execute(
            "SELECT id FROM sections WHERE class_id=? AND name=?", (body.class_id, name)).fetchone()
        if dup:
            return json_err("This section already exists for this class", 400)

        sid = new_id("sec")
        conn.execute("INSERT INTO sections (id, name, class_id) VALUES (?,?,?)",
                     (sid, name, body.class_id))
        audit(session, "Sections", "Create", f"Added section {name}", conn=conn)
        conn.commit()
        return {"id": sid}
    finally:
        conn.close()


@router.delete("/sections/{sid}")
def delete_section(sid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
        if not existing:
            return json_err("Section not found", 404)

        students = conn.execute("SELECT COUNT(*) c FROM students WHERE section_id=?", (sid,)).fetchone()["c"]
        if students:
            return json_err("Cannot delete a section with enrolled students", 400)

        conn.execute("DELETE FROM sections WHERE id=?", (sid,))
        audit(session, "Sections", "Delete", f"Removed section {sid}", conn=conn)
        conn.commit()
        return {"message": "Section removed"}
    finally:
        conn.close()