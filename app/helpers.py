"""Shared business helpers: grading, audit logging, school lookup."""
import datetime

from app.config import GRADE_SCALE, DEFAULT_PASS_MARK, SYSTEM_USER_ID, SYSTEM_USER_NAME
from app.db import get_conn
import secrets


def compute_grade(percentage) -> str:
    percentage = float(percentage)
    for threshold, grade in GRADE_SCALE:
        if percentage >= threshold:
            return grade
    return "F"


def compute_pass_fail(percentage, pass_mark: float = DEFAULT_PASS_MARK) -> str:
    return "Pass" if float(percentage) >= pass_mark else "Fail"


def audit(session_user, module: str, action: str, description: str, conn=None):
    """Write one audit_log row. session_user is the decoded session dict, or
    None for automated/system actions (uses the seeded System user)."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    if session_user:
        uid = session_user.get("uid", SYSTEM_USER_ID)
        name = session_user.get("name", SYSTEM_USER_NAME)
        role = session_user.get("role", "system")
    else:
        uid, name, role = SYSTEM_USER_ID, SYSTEM_USER_NAME, "system"

    now = datetime.datetime.now()
    log_id = f"alog_{now.strftime('%Y%m%d%H%M%S')}_{now.microsecond}_{secrets.token_hex(3)}"
    conn.execute(
        "INSERT INTO audit_log (id, user_id, user_name, role, module, action, date, time, description) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (log_id, uid, name, role,
         module, action, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), description),
    )
    if own_conn:
        conn.commit()
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
    except Exception:
        return str(num)