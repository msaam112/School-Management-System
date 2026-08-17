"""Shared business helpers: grading, audit logging, school lookup."""
import datetime
import logging
import secrets

from app.config import GRADE_SCALE, DEFAULT_PASS_MARK, SYSTEM_USER_ID, SYSTEM_USER_NAME
from app.db import get_conn

logger = logging.getLogger("sms.helpers")


def compute_grade(percentage) -> str:
    try:
        percentage = float(percentage)
    except (TypeError, ValueError):
        logger.warning("compute_grade received a non-numeric percentage: %r", percentage)
        return "F"
    for threshold, grade in GRADE_SCALE:
        if percentage >= threshold:
            return grade
    return "F"


def get_pass_mark(conn=None) -> float:
    """Reads the school-configured pass mark from Settings, falling back
    to DEFAULT_PASS_MARK if it hasn't been configured yet or is invalid."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='pass_mark'").fetchone()
        if row and row["value"] not in (None, ""):
            return float(row["value"])
    except (TypeError, ValueError):
        logger.warning("Configured pass_mark setting is not a valid number: %r", row["value"] if row else None)
    finally:
        if own_conn:
            conn.close()
    return DEFAULT_PASS_MARK


def compute_pass_fail(percentage, pass_mark: float = None, conn=None) -> str:
    """If pass_mark isn't explicitly passed, uses the school's configured
    Pass Mark % setting (falling back to DEFAULT_PASS_MARK if unset)."""
    try:
        percentage = float(percentage)
    except (TypeError, ValueError):
        logger.warning("compute_pass_fail received a non-numeric percentage: %r", percentage)
        return "Fail"

    if pass_mark is None:
        pass_mark = get_pass_mark(conn)

    return "Pass" if percentage >= pass_mark else "Fail"


def audit(session_user, module: str, action: str, description: str, conn=None):
    """Write one audit_log row. session_user is the decoded session dict, or
    None for automated/system actions (uses the seeded System user)."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    if session_user:
        uid = session_user.get("uid") or SYSTEM_USER_ID
        name = session_user.get("name") or SYSTEM_USER_NAME
        role = session_user.get("role") or "system"
    else:
        uid, name, role = SYSTEM_USER_ID, SYSTEM_USER_NAME, "system"

    now = datetime.datetime.now()
    log_id = f"alog_{now.strftime('%Y%m%d%H%M%S')}_{now.microsecond}_{secrets.token_hex(3)}"
    try:
        conn.execute(
            "INSERT INTO audit_log (id, user_id, user_name, role, module, action, date, time, description) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (log_id, uid, name, role,
             module, action, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), description),
        )
        if own_conn:
            conn.commit()
    except Exception:
        # An audit-log write failing should never take down the request that
        # triggered it, but it absolutely should be visible in server logs.
        logger.exception("Failed to write audit log entry: module=%s action=%s", module, action)
    finally:
        if own_conn:
            conn.close()


def get_school(conn=None) -> dict:
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    row = conn.execute("SELECT * FROM school WHERE id=1").fetchone()
    if own_conn:
        conn.close()
    return dict(row) if row else {}


def is_setup_done(conn=None) -> bool:
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    row = conn.execute("SELECT setup_done FROM school WHERE id=1").fetchone()
    if own_conn:
        conn.close()
    return bool(row and row["setup_done"])


def month_name(num) -> str:
    months = ["", "January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    try:
        return months[int(num)]
    except (TypeError, ValueError, IndexError):
        return str(num)