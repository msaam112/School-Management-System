"""Shared FastAPI dependencies for auth/role enforcement.
Every protected router imports from here instead of re-checking sessions manually.
"""
from fastapi import Request, HTTPException

from app.main import get_session


def require_session(request: Request) -> dict:
    """Raise 401 if not logged in; otherwise return the session dict."""
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
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