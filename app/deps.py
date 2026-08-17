"""Shared FastAPI dependencies for auth/role enforcement.
Every protected router imports from here instead of re-checking sessions manually.
"""
from fastapi import Request, HTTPException

from app.main import get_session
from app.db import get_conn


def require_session(request: Request) -> dict:
    """Raise 401 if not logged in; otherwise return the session dict.

    Also re-verifies the user's live status and role against the database
    on every request (not just at login) — so disabling an account or
    changing someone's role takes effect immediately, rather than only
    once their existing session cookie eventually expires.
    """
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Parent sessions aren't backed by a `users` row (see auth.py), so this
    # live re-check only applies to staff roles.
    if session.get("role") != "parent":
        conn = get_conn()
        try:
            row = conn.execute(
            "SELECT status, role, display_name FROM users WHERE id=?", (session.get("uid"),)
        ).fetchone()
        finally:
            conn.close()

        if not row or row["status"] != "active":
            raise HTTPException(status_code=401, detail="This account is no longer active")

        # Reflect the current role, in case it was changed after this
        # session was issued.
        session = dict(session)
        session["role"] = row["role"]
        if row["display_name"]:
            session["name"] = row["display_name"]

    return session


def require_role(*allowed_roles: str):
    """Returns a FastAPI dependency that enforces the caller's role is in allowed_roles.
    Usage: session = Depends(require_role("super_admin", "principal"))
    """
    def _dep(request: Request) -> dict:
        session = require_session(request)
        if session.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return session
    return _dep