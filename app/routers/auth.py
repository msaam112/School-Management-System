"""Auth & Setup Wizard — FR-1, FR-2, UC-1."""
import re
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from typing import Optional, List

from app.config import MAX_SECTIONS_PER_CLASS
from app.db import get_conn, now_iso
from app.security import hash_password, verify_password, new_id, create_session
from app.helpers import audit, is_setup_done
from app.main import get_session, set_session_cookie, clear_session_cookie, json_err

router = APIRouter(prefix="/api", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ models
class ClassInput(BaseModel):
    name: str
    sections: List[str] = []


class SetupRequest(BaseModel):
    school_name: str
    admin_email: str
    admin_password: str
    address: Optional[str] = None
    emis_code: Optional[str] = None
    contact_number: Optional[str] = None
    principal_name: Optional[str] = None
    established_year: Optional[str] = None
    motto: Optional[str] = None
    logo: Optional[str] = None
    classes: List[ClassInput] = []


class StaffLoginRequest(BaseModel):
    type: str = "staff"
    email: str
    password: str


class ParentLoginRequest(BaseModel):
    type: str = "parent"
    cnic: str
    roll: str


# ------------------------------------------------------------------ setup
@router.get("/setup/status")
def setup_status():
    return {"setup_done": is_setup_done()}


@router.post("/setup")
def setup(body: SetupRequest, response: Response):
    conn = get_conn()
    try:
        if is_setup_done(conn):
            return json_err("School already configured", 400)

        name = body.school_name.strip()
        if not name:
            return json_err("School name is required", 400)

        email = body.admin_email.strip().lower()
        if not EMAIL_RE.match(email):
            return json_err("Valid admin email is required", 400)

        if len(body.admin_password) < 6:
            return json_err("Admin password must be at least 6 characters", 400)

        if not body.classes:
            return json_err("At least one class is required", 400)

        conn.execute(
            "INSERT INTO school (id, name, logo, address, emis_code, contact_number, "
            "principal_name, setup_done, established_year, motto) VALUES (1,?,?,?,?,?,?,1,?,?)",
            (name, body.logo, body.address, body.emis_code, body.contact_number,
             body.principal_name, body.established_year, body.motto),
        )

        uid = new_id("usr")
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, status, display_name, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, email, hash_password(body.admin_password), "super_admin", "active",
             name or "Super Admin", now_iso()),
        )

        for c in body.classes:
            cname = c.name.strip()
            if not cname:
                continue
            cid = new_id("cls")
            conn.execute("INSERT INTO classes (id, name) VALUES (?,?)", (cid, cname))
            for sname in c.sections[:MAX_SECTIONS_PER_CLASS]:
                sname = str(sname).strip()
                if sname:
                    conn.execute("INSERT INTO sections (id, name, class_id) VALUES (?,?,?)",
                                 (new_id("sec"), sname, cid))

        session_user = {"uid": uid, "role": "super_admin", "name": name or "Super Admin"}
        audit(session_user, "Setup", "School Setup", f"Initial setup for '{name}' completed", conn=conn)
        conn.commit()

        token = create_session(session_user)
        set_session_cookie(response, token)
        return {"role": "super_admin", "name": name}
    finally:
        conn.close()


# ------------------------------------------------------------------ login/logout/me
@router.post("/auth/login")
def login(body: dict, response: Response):
    conn = get_conn()
    try:
        if body.get("type") == "parent":
            cnic = (body.get("cnic") or "").strip().lower()
            roll = (body.get("roll") or "").strip()
            student = conn.execute("SELECT * FROM students WHERE roll_number=?", (roll,)).fetchone()
            if not student:
                return json_err("Invalid roll number", 401)
            parent = conn.execute("SELECT * FROM parents WHERE id=?", (student["parent_id"],)).fetchone()
            if not parent or (parent["cnic"] or "").strip().lower() != cnic:
                return json_err("CNIC does not match our records", 401)
            session_user = {"uid": parent["id"], "role": "parent",
                             "name": parent["name"], "student_id": student["id"]}
            token = create_session(session_user)
            set_session_cookie(response, token)
            return {"role": "parent", "name": parent["name"]}

        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return json_err("Invalid email or password", 401)
        if user["status"] != "active":
            return json_err("Account is disabled", 403)

        session_user = {"uid": user["id"], "role": user["role"],
                         "name": user["display_name"] or user["email"]}
        token = create_session(session_user)
        set_session_cookie(response, token)
        return {"role": user["role"], "name": session_user["name"]}
    finally:
        conn.close()


@router.post("/auth/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"message": "Logged out"}


@router.get("/auth/me")
def me(request: Request):
    session = get_session(request)
    if not session:
        return json_err("Not authenticated", 401)

    conn = get_conn()
    try:
        role = session["role"]
        data = {"role": role, "name": session.get("name"), "uid": session.get("uid")}

        if role == "parent":
            sid = session.get("student_id")
            stu = conn.execute(
                "SELECT s.*, c.name as class_name, sec.name as section_name FROM students s "
                "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
                "WHERE s.id=?", (sid,)).fetchone()
            data["student"] = dict(stu) if stu else None
        elif role in ("teacher", "class_incharge"):
            t = conn.execute("SELECT * FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
            data["teacher"] = dict(t) if t else None

        return data
    finally:
        conn.close()