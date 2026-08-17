"""System Settings & User Privileges — FR-18."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Dict

from app.config import ROLES
from app.db import get_conn
from app.helpers import audit, get_school
from app.security import hash_password, random_password, PasswordError
from app.deps import require_role
from app.main import json_err

import os
import uuid
from fastapi import UploadFile, File
from app.config import UPLOAD_DIR
from app.deps import require_role, require_session

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None


@router.get("/profile")
def get_profile(session: dict = Depends(require_session)):
    conn = get_conn()
    try:
        u = conn.execute("SELECT email, display_name, role FROM users WHERE id=?", (session["uid"],)).fetchone()
        if not u:
            return json_err("User not found", 404)
        return {"email": u["email"], "display_name": u["display_name"], "role": u["role"]}
    finally:
        conn.close()


@router.put("/profile")
def update_profile(body: ProfileUpdate, session: dict = Depends(require_session)):
    conn = get_conn()
    try:
        sets, params = [], []
        if body.display_name is not None:
            name = body.display_name.strip()
            if not name:
                return json_err("Name cannot be empty", 400)
            sets.append("display_name=?")
            params.append(name)
        if body.password is not None:
            try:
                ph = hash_password(body.password)
            except PasswordError as e:
                return json_err(str(e), 400)
            sets.append("password_hash=?")
            params.append(ph)
        if not sets:
            return json_err("Nothing to update", 400)

        conn.execute("UPDATE users SET " + ", ".join(sets) + " WHERE id=?", params + [session["uid"]])
        audit(session, "Settings", "Update", "User updated their own profile", conn=conn)
        conn.commit()
        return {"message": "Profile updated"}
    finally:
        conn.close()

router = APIRouter(prefix="/api/settings", tags=["settings"])

REASSIGNABLE_ROLES = [r for r in ROLES if r != "system"]  # never reassign anyone to the internal system role


class SchoolSettingsUpdate(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    address: Optional[str] = None
    emis_code: Optional[str] = None
    contact_number: Optional[str] = None
    principal_name: Optional[str] = None
    established_year: Optional[str] = None
    motto: Optional[str] = None
    settings: Optional[Dict[str, str]] = None


class UserStatusUpdate(BaseModel):
    status: str  # "active" | "disabled"


class SetPasswordRequest(BaseModel):
    password: str


class RoleChangeRequest(BaseModel):
    role: str


def _active_super_admin_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM users WHERE role='super_admin' AND status='active'"
    ).fetchone()["c"]


# ------------------------------------------------------------------ school + general settings
@router.get("")
def get_settings(session: dict = Depends(require_role(
        "super_admin", "principal", "teacher", "class_incharge"))):
    conn = get_conn()
    try:
        school = get_school(conn)
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {r["key"]: r["value"] for r in rows}
        return {"school": school, "settings": settings}
    finally:
        conn.close()


@router.put("")
def update_settings(body: SchoolSettingsUpdate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        sets, params = [], []
        for f in ["name", "logo", "address", "emis_code", "contact_number",
                  "principal_name", "established_year", "motto"]:
            v = getattr(body, f)
            if v is not None:
                sets.append(f"{f}=?")
                params.append(v)
        if sets:
            conn.execute("UPDATE school SET " + ", ".join(sets) + " WHERE id=1", params)

        for k, v in (body.settings or {}).items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))

        audit(session, "Settings", "Update", "School/system settings updated", conn=conn)
        conn.commit()
        return {"message": "Settings updated"}
    finally:
        conn.close()


# ------------------------------------------------------------------ user privileges
@router.get("/users")
def list_users(session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, email, role, status, display_name, created_at FROM users "
            "WHERE role != 'system' ORDER BY role, display_name").fetchall()
        return {"users": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.put("/users/{uid}/status")
def set_user_status(uid: str, body: UserStatusUpdate, session: dict = Depends(require_role("super_admin"))):
    if body.status not in ("active", "disabled"):
        return json_err("Status must be 'active' or 'disabled'", 400)

    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return json_err("User not found", 404)
        if user["role"] == "system":
            return json_err("Cannot disable the System account", 400)

        if (user["role"] == "super_admin" and body.status == "disabled"
                and _active_super_admin_count(conn) <= 1):
            return json_err("Cannot disable the last remaining active Super Admin", 400)

        conn.execute("UPDATE users SET status=? WHERE id=?", (body.status, uid))
        audit(session, "Settings", "Permission Change",
              f"Set user {user['email']} status to {body.status}", conn=conn)
        conn.commit()
        return {"message": f"User {body.status}"}
    finally:
        conn.close()


@router.post("/users/{uid}/reset-password")
def reset_password(uid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return json_err("User not found", 404)
        if user["role"] == "system":
            return json_err("Cannot reset the System account", 400)

        new_password = random_password()
        try:
            password_hash = hash_password(new_password)
        except PasswordError as e:
            return json_err(str(e), 400)

        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))
        audit(session, "Settings", "Permission Change",
              f"Reset password for user {user['email']}", conn=conn)
        conn.commit()
        return {"message": "Password reset", "password": new_password}
    finally:
        conn.close()


@router.post("/users/{uid}/set-password")
def set_custom_password(uid: str, body: SetPasswordRequest, session: dict = Depends(require_role("super_admin"))):
    """Sets a SPECIFIC password chosen by Super Admin, as opposed to
    reset-password which always generates a random one."""
    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return json_err("User not found", 404)
        if user["role"] == "system":
            return json_err("Cannot set a password for the System account", 400)

        try:
            password_hash = hash_password(body.password)
        except PasswordError as e:
            return json_err(str(e), 400)

        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))
        audit(session, "Settings", "Permission Change",
              f"Set a custom password for user {user['email']}", conn=conn)
        conn.commit()
        return {"message": "Password updated"}
    finally:
        conn.close()


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), session: dict = Depends(require_role("super_admin"))):
    if not file.content_type or not file.content_type.startswith("image/"):
        return json_err("File must be an image", 400)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return json_err("Unsupported image format. Use PNG, JPG, GIF, or WEBP.", 400)

    contents = await file.read()
    if len(contents) > 3 * 1024 * 1024:
        return json_err("Logo image must be under 3MB", 400)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"logo_{uuid.uuid4().hex[:10]}{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
        f.write(contents)

    url = f"/static/uploads/{fname}"
    conn = get_conn()
    try:
        conn.execute("UPDATE school SET logo=? WHERE id=1", (url,))
        audit(session, "Settings", "Update", "School logo updated", conn=conn)
        conn.commit()
    finally:
        conn.close()
    return {"logo": url}

@router.put("/users/{uid}/role")
def change_user_role(uid: str, body: RoleChangeRequest, session: dict = Depends(require_role("super_admin"))):
    """Free role reassignment: Super Admin can change any user's role to
    any other role, with guards against locking the school out of admin
    access (self-demotion of the last active Super Admin) and against
    orphaning teacher/principal profile data.
    """
    if body.role not in REASSIGNABLE_ROLES:
        return json_err(f"Invalid role. Must be one of: {', '.join(REASSIGNABLE_ROLES)}", 400)

    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return json_err("User not found", 404)
        if user["role"] == "system":
            return json_err("Cannot change the role of the System account", 400)

        old_role = user["role"]
        if old_role == body.role:
            return json_err(f"This user already has the '{body.role}' role", 400)

        # Guard: never leave the school with zero active Super Admins.
        if old_role == "super_admin" and body.role != "super_admin":
            if _active_super_admin_count(conn) <= 1:
                return json_err(
                    "Cannot reassign the last remaining active Super Admin to a different role. "
                    "Promote another user to Super Admin first.",
                    400
                )

        # If this user has a teachers/principals profile row tied to their
        # OLD role, that link becomes stale once their role changes — warn
        # rather than silently leaving orphaned profile data behind.
        warning = None
        if old_role in ("teacher", "class_incharge"):
            t = conn.execute("SELECT id FROM teachers WHERE user_id=?", (uid,)).fetchone()
            if t:
                warning = (
                    "This user has an existing Teacher profile (qualifications, class assignments, etc.) "
                    "which is NOT automatically removed or transferred. If they no longer need it, "
                    "manage it separately from the Teachers page."
                )
        elif old_role == "principal":
            p = conn.execute("SELECT id FROM principals WHERE user_id=?", (uid,)).fetchone()
            if p:
                warning = (
                    "This user has an existing Principal profile which is NOT automatically removed. "
                    "Manage it separately from Principal management if needed."
                )

        conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
        audit(session, "Settings", "Permission Change",
              f"Changed role of user {user['email']} from '{old_role}' to '{body.role}'", conn=conn)
        conn.commit()

        response = {"message": f"Role changed to {body.role}"}
        if warning:
            response["warning"] = warning
        return response
    finally:
        conn.close()