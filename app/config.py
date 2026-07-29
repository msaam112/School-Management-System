"""Global configuration for the SMS backend.

All values are overridable via environment variables so the same code
runs unchanged in dev, test, and production.
"""
import os
from pathlib import Path

# Project root = the folder that contains app/, static/, tests/
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get("SMS_DB", str(BASE_DIR / "sms.db"))
BACKUP_DIR = os.environ.get("SMS_BACKUP_DIR", str(BASE_DIR / "backups"))
STATIC_DIR = str(BASE_DIR / "static")

# CHANGE THIS before any real deployment.
SECRET_KEY = os.environ.get("SMS_SECRET", "dev-secret-change-me-8f3c21a9")

HOST = os.environ.get("SMS_HOST", "0.0.0.0")
PORT = int(os.environ.get("SMS_PORT", "8000"))

SESSION_TTL_SECONDS = 60 * 60 * 12  # 12 hours, per FR-1.3 session management

# ---- Roles (SRS §2.3 / §9) ----
ROLES = ["super_admin", "principal", "teacher", "class_incharge", "parent", "system"]
STAFF_ROLES = ["super_admin", "principal", "teacher", "class_incharge"]  # email+password login
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
DEFAULT_PASS_MARK = 33.0

# ---- Seeded system account (satisfies audit_log FK per SRS §6.4) ----
SYSTEM_USER_ID = "usr_system"
SYSTEM_USER_EMAIL = "system@internal.sms"
SYSTEM_USER_NAME = "System"