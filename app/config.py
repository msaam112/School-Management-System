"""Global configuration for the SMS backend.

All values are overridable via environment variables so the same code
runs unchanged in dev, test, and production.
"""
import os
import secrets
from pathlib import Path

# Project root = the folder that contains app/, static/, tests/
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get("SMS_DB", str(BASE_DIR / "sms.db"))
BACKUP_DIR = os.environ.get("SMS_BACKUP_DIR", str(BASE_DIR / "backups"))
UPLOAD_DIR = os.environ.get("SMS_UPLOAD_DIR", str(BASE_DIR / "static" / "uploads"))
STATIC_DIR = str(BASE_DIR / "static")

ENVIRONMENT = os.environ.get("SMS_ENV", "development")  # "development" | "production"


def _load_or_create_secret_key() -> str:
    """Session cookies are signed with this key. Never fall back to a
    hardcoded value — that would be a real vulnerability the moment this
    (public) repo is deployed without SMS_SECRET explicitly set.

    Resolution order:
      1. SMS_SECRET environment variable (recommended for real deployments)
      2. A previously auto-generated key persisted at BASE_DIR/.secret_key
      3. A freshly generated key, persisted for next time
    """
    env_secret = os.environ.get("SMS_SECRET")
    if env_secret:
        return env_secret

    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()

    generated = secrets.token_hex(32)
    try:
        key_file.write_text(generated)
    except OSError:
        # Read-only filesystem (some hosting platforms) — the key just
        # won't survive a restart there. Setting SMS_SECRET explicitly
        # is the correct fix for those environments.
        pass
    return generated


SECRET_KEY = _load_or_create_secret_key()

HOST = os.environ.get("SMS_HOST", "0.0.0.0")
# Most hosting platforms (Render, Heroku, etc.) inject their own PORT env
# var and expect the app to bind to it — check that before our own SMS_PORT.
PORT = int(os.environ.get("PORT", os.environ.get("SMS_PORT", "8000")))

SESSION_TTL_SECONDS = 60 * 60 * 12  # 12 hours, per FR-1.3 session management

# ---- Roles (SRS §2.3 / §9) ----
ROLES = ["super_admin", "principal", "teacher", "class_incharge", "parent", "system"]
STAFF_ROLES = ["super_admin", "principal", "teacher", "class_incharge"]  # email+password login
# Deliberately a separate list from STAFF_ROLES, even though identical today —
# these are allowed to diverge later (e.g. a staff role that can log in
# but shouldn't see the admin portal UI).
ADMIN_ROLES = ["super_admin", "principal", "teacher", "class_incharge"]  # admin portal access

# ---- Business rules (SRS §2.5, FR-7.2) ----
MAX_SECTIONS_PER_CLASS = 3

# ---- Attendance / Fees (FR-9, FR-10, FR-14) ----
ATTENDANCE_STATUSES = ["Present", "Absent", "Leave"]
PAYMENT_STATUSES = ["Paid", "Unpaid", "Partially Paid"]

# ---- Grading (FR-12) ----
GRADE_SCALE = [
    (90, "A+"), (80, "A"), (70, "B"), (60, "C"),
    (50, "D"), (40, "E"), (0, "F"),
]
# NOTE: This is only the fallback used if the school hasn't configured a
# pass mark via System Settings. As of this review, the Settings page's
# "Pass Mark %" field is NOT yet wired into actual grading — see the
# helpers.py / examinations.py review for the fix that connects them.
DEFAULT_PASS_MARK = 33.0

# ---- Seeded system account (satisfies audit_log FK per SRS §6.4) ----
SYSTEM_USER_ID = "usr_system"
SYSTEM_USER_EMAIL = "system@internal.sms"
SYSTEM_USER_NAME = "System"