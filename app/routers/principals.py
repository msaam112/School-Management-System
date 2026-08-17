"""Principal (Headmaster) Management — dedicated flow, separate from Teachers."""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.db import get_conn, now_iso, today
from app.security import new_id, hash_password, random_password, PasswordError
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/principals", tags=["principals"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PrincipalCreate(BaseModel):
    name: str
    email: str
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    joining_date: Optional[str] = None
    password: Optional[str] = None


class PrincipalUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    joining_date: Optional[str] = None
    employment_status: Optional[str] = None


@router.get("")
def list_principals(session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT p.*, u.status user_status FROM principals p LEFT JOIN users u ON p.user_id=u.id "
            "ORDER BY p.name").fetchall()
        return {"principals": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_principal(body: PrincipalCreate, session: dict = Depends(require_role("super_admin"))):
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name or not EMAIL_RE.match(email):
        return json_err("Name and a valid email are required", 400)

    conn = get_conn()
    try:
        dup = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if dup:
            return json_err("A user with this email already exists", 400)

        emp_id = body.employee_id or f"HM-{new_id('')[-6:]}"
        dup_emp = conn.execute("SELECT id FROM principals WHERE employee_id=?", (emp_id,)).fetchone()
        if dup_emp:
            return json_err("Employee ID already in use", 400)

        password = body.password or random_password()
        try:
            password_hash = hash_password(password)
        except PasswordError as e:
            return json_err(str(e), 400)

        uid = new_id("usr")
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, status, display_name, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, email, password_hash, "principal", "active", name, now_iso()))

        pid = new_id("prin")
        conn.execute(
            "INSERT INTO principals (id, employee_id, name, email, phone, qualification, joining_date, "
            "employment_status, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, emp_id, name, email, body.phone, body.qualification,
             body.joining_date or today(), "active", uid))

        audit(session, "Principals", "Create", f"Added headmaster {name} ({email})", conn=conn)
        conn.commit()
        return {"id": pid, "password": password, "message": "Headmaster account created"}
    finally:
        conn.close()


@router.put("/{pid}")
def update_principal(pid: str, body: PrincipalUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM principals WHERE id=?", (pid,)).fetchone()
        if not existing:
            return json_err("Headmaster not found", 404)

        if body.email is not None:
            email = body.email.strip().lower()
            if not EMAIL_RE.match(email):
                return json_err("A valid email is required", 400)
            dup = conn.execute("SELECT id FROM users WHERE email=? AND id!=?",
                                (email, existing["user_id"])).fetchone()
            if dup:
                return json_err("Another user already uses this email", 400)
            conn.execute("UPDATE users SET email=? WHERE id=?", (email, existing["user_id"]))

        sets, params = [], []
        for f in ["name", "email", "phone", "qualification", "joining_date", "employment_status", "employee_id"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v.strip().lower() if f == "email" else v)
        if sets:
            conn.execute("UPDATE principals SET " + ", ".join(sets) + " WHERE id=?", params + [pid])
            audit(session, "Principals", "Update", f"Updated headmaster '{existing['name']}'", conn=conn)
            conn.commit()
        return {"message": "Headmaster updated"}
    finally:
        conn.close()


@router.delete("/{pid}")
def delete_principal(pid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM principals WHERE id=?", (pid,)).fetchone()
        if not p:
            return json_err("Headmaster not found", 404)

        conn.execute("DELETE FROM principals WHERE id=?", (pid,))
        if p["user_id"]:
            conn.execute("DELETE FROM users WHERE id=?", (p["user_id"],))

        audit(session, "Principals", "Delete", f"Removed headmaster '{p['name']}'", conn=conn)
        conn.commit()
        return {"message": "Headmaster removed"}
    finally:
        conn.close()