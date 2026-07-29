"""Teacher Management — FR-6, UC-3."""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn, now_iso, today
from app.security import new_id, hash_password, random_password
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/teachers", tags=["teachers"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VIEW_ROLES = ("super_admin", "principal")


class TeacherCreate(BaseModel):
    name: str
    email: str
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    joining_date: Optional[str] = None
    employment_status: Optional[str] = "active"
    is_class_incharge: Optional[bool] = False
    class_id: Optional[str] = None
    password: Optional[str] = None


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    joining_date: Optional[str] = None
    employment_status: Optional[str] = None
    is_class_incharge: Optional[bool] = None
    class_id: Optional[str] = None


@router.get("")
def list_teachers(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT t.*, c.name class_name, u.email login_email, u.status user_status FROM teachers t "
            "LEFT JOIN classes c ON t.class_id=c.id LEFT JOIN users u ON t.user_id=u.id "
            "ORDER BY t.name").fetchall()
        return {"teachers": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_teacher(body: TeacherCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name or not EMAIL_RE.match(email):
        return json_err("Name and a valid email are required", 400)

    conn = get_conn()
    try:
        dup = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if dup:
            return json_err("A user with this email already exists", 400)

        emp_id = body.employee_id or f"EMP-{new_id('')[-6:]}"
        dup_emp = conn.execute("SELECT id FROM teachers WHERE employee_id=?", (emp_id,)).fetchone()
        if dup_emp:
            return json_err("Employee ID already in use", 400)

        password = body.password or random_password()
        is_ci = 1 if body.is_class_incharge else 0
        role = "class_incharge" if is_ci else "teacher"

        uid = new_id("usr")
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, status, display_name, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, email, hash_password(password), role, "active", name, now_iso()))

        tid = new_id("tch")
        conn.execute(
            "INSERT INTO teachers (id, employee_id, name, email, phone, qualification, joining_date, "
            "employment_status, is_class_incharge, class_id, user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tid, emp_id, name, email, body.phone, body.qualification,
             body.joining_date or today(), body.employment_status or "active",
             is_ci, body.class_id if is_ci else None, uid))

        audit(session, "Teachers", "Create", f"Added teacher {name} ({email})", conn=conn)
        conn.commit()
        return {"id": tid, "password": password, "message": "Teacher added"}
    finally:
        conn.close()


@router.put("/{tid}")
def update_teacher(tid: str, body: TeacherUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM teachers WHERE id=?", (tid,)).fetchone()
        if not existing:
            return json_err("Teacher not found", 404)

        sets, params = [], []
        for f in ["name", "email", "phone", "qualification", "joining_date",
                  "employment_status", "employee_id"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v)

        # class_id is only meaningful when is_class_incharge is true — never store
        # a stray class assignment for a regular teacher, regardless of what was sent.
        if body.is_class_incharge is not None:
            sets.append("is_class_incharge=?")
            params.append(1 if body.is_class_incharge else 0)
            sets.append("class_id=?")
            params.append(body.class_id if body.is_class_incharge else None)
        elif body.class_id is not None:
            # is_class_incharge wasn't part of this update — only allow class_id
            # to be set if the teacher is already an incharge.
            current_ci = conn.execute(
                "SELECT is_class_incharge FROM teachers WHERE id=?", (tid,)).fetchone()["is_class_incharge"]
            if current_ci:
                sets.append("class_id=?")
                params.append(body.class_id)
        if sets:
            conn.execute("UPDATE teachers SET " + ", ".join(sets) + " WHERE id=?", params + [tid])

            # Keep the linked user's role in sync with the class-incharge flag
            if body.is_class_incharge is not None and existing["user_id"]:
                new_role = "class_incharge" if body.is_class_incharge else "teacher"
                conn.execute("UPDATE users SET role=? WHERE id=?", (new_role, existing["user_id"]))

            audit(session, "Teachers", "Update", f"Updated teacher {tid}", conn=conn)
            conn.commit()
        return {"message": "Teacher updated"}
    finally:
        conn.close()


@router.delete("/{tid}")
def delete_teacher(tid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        t = conn.execute("SELECT * FROM teachers WHERE id=?", (tid,)).fetchone()
        if not t:
            return json_err("Teacher not found", 404)

        conn.execute("DELETE FROM teacher_assignments WHERE teacher_id=?", (tid,))
        conn.execute("DELETE FROM teachers WHERE id=?", (tid,))
        if t["user_id"]:
            conn.execute("DELETE FROM users WHERE id=?", (t["user_id"],))

        audit(session, "Teachers", "Delete", f"Removed teacher {tid}", conn=conn)
        conn.commit()
        return {"message": "Teacher removed"}
    finally:
        conn.close()