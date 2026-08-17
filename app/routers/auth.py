"""Auth & Setup Wizard — FR-1, FR-2, UC-1."""
import re
import time
import sqlite3
from collections import defaultdict, deque
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from typing import Optional, List, Union, Literal

from app.config import MAX_SECTIONS_PER_CLASS
from app.db import get_conn, now_iso
from app.security import hash_password, verify_password, new_id, create_session, PasswordError
from app.helpers import audit, is_setup_done
from app.main import get_session, set_session_cookie, clear_session_cookie, json_err

router = APIRouter(prefix="/api", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A pre-computed dummy hash used to keep login timing consistent whether or
# not the account actually exists — prevents timing-based account enumeration.
_DUMMY_HASH = hash_password("this-is-a-dummy-password-never-used")

# ------------------------------------------------------------------ simple in-memory rate limiter
# Appropriate for a single-instance deployment (Render free tier). If this
# ever runs across multiple instances, this should move to a shared store
# (e.g. Redis) instead — flagging for future scaling, not a bug today.
_LOGIN_ATTEMPTS: dict = defaultdict(deque)
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes


def _rate_limited(identifier: str) -> bool:
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[identifier]
    while attempts and now - attempts[0] > RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        return True
    attempts.append(now)
    return False


def _normalize_cnic(cnic: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", cnic or "").lower()


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
    type: Literal["staff"] = "staff"
    email: str
    password: str


class ParentLoginRequest(BaseModel):
    type: Literal["parent"] = "parent"
    cnic: str
    roll: str


LoginRequest = Union[StaffLoginRequest, ParentLoginRequest]


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

        try:
            password_hash = hash_password(body.admin_password)
        except PasswordError as e:
            return json_err(str(e), 400)

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
            (uid, email, password_hash, "super_admin", "active",
             name or "Super Admin", now_iso()),
        )

        try:
            for c in body.classes:
                cname = c.name.strip()
                if not cname:
                    continue
                cid = new_id("cls")
                conn.execute("INSERT INTO classes (id, name) VALUES (?,?)", (cid, cname))
                seen_sections = set()
                for sname in c.sections[:MAX_SECTIONS_PER_CLASS]:
                    sname = str(sname).strip()
                    if not sname or sname.lower() in seen_sections:
                        continue  # skip blanks and duplicates within the same class
                    seen_sections.add(sname.lower())
                    conn.execute("INSERT INTO sections (id, name, class_id) VALUES (?,?,?)",
                                 (new_id("sec"), sname, cid))
        except sqlite3.IntegrityError:
            conn.rollback()
            return json_err("Duplicate class or section name detected. Please use unique names.", 400)

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
def login(body: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"

    if isinstance(body, ParentLoginRequest):
        rate_key = f"parent:{client_ip}:{_normalize_cnic(body.cnic)}"
        if _rate_limited(rate_key):
            return json_err("Too many login attempts. Please wait a few minutes and try again.", 429)

        conn = get_conn()
        try:
            cnic = _normalize_cnic(body.cnic)
            roll = (body.roll or "").strip()
            student = conn.execute("SELECT * FROM students WHERE roll_number=?", (roll,)).fetchone()
            if not student:
                return json_err("Invalid roll number", 401)
            parent = conn.execute("SELECT * FROM parents WHERE id=?", (student["parent_id"],)).fetchone()
            if not parent or _normalize_cnic(parent["cnic"]) != cnic:
                return json_err("CNIC does not match our records", 401)

            session_user = {"uid": parent["id"], "role": "parent",
                             "name": parent["name"], "student_id": student["id"]}
            token = create_session(session_user)
            set_session_cookie(response, token)
            return {"role": "parent", "name": parent["name"]}
        finally:
            conn.close()

    # Staff login
    email = body.email.strip().lower()
    rate_key = f"staff:{client_ip}:{email}"
    if _rate_limited(rate_key):
        return json_err("Too many login attempts. Please wait a few minutes and try again.", 429)

    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        # Always run password verification, even for a nonexistent account,
        # so response timing can't be used to enumerate valid emails.
        stored_hash = user["password_hash"] if user else _DUMMY_HASH
        password_ok = verify_password(body.password, stored_hash)

        if not user or not password_ok:
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
        display_name = session.get("name")
        if role != "parent":
            u = conn.execute("SELECT display_name FROM users WHERE id=?", (session["uid"],)).fetchone()
            if u and u["display_name"]:
                display_name = u["display_name"]
        data = {"role": role, "name": display_name, "uid": session.get("uid")}

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
        elif role == "principal":
            p = conn.execute("SELECT * FROM principals WHERE user_id=?", (session["uid"],)).fetchone()
            data["principal"] = dict(p) if p else None

        return data
    finally:
        conn.close()