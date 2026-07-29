"""System Settings & User Privileges — FR-18."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Dict

from app.db import get_conn
from app.helpers import audit, get_school
from app.security import hash_password, random_password
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
        if user["role"] in ("super_admin", "system"):
            return json_err("Cannot disable a Super Admin or the System account", 400)

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
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (hash_password(new_password), uid))
        audit(session, "Settings", "Permission Change",
              f"Reset password for user {user['email']}", conn=conn)
        conn.commit()
        return {"message": "Password reset", "password": new_password}
    finally:
        conn.close()