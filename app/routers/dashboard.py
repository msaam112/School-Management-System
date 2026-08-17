"""Dashboard — FR-3. Role-based summary data for the landing page."""
from fastapi import APIRouter, Depends

from app.db import get_conn, today
from app.helpers import get_school
from app.deps import require_session

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(session: dict = Depends(require_session)):
    conn = get_conn()
    try:
        role = session["role"]
        out = {"role": role, "school": get_school(conn), "name": session.get("name")}

        if role == "super_admin":
            # FR-3.2: totals + today's attendance + pending fees.
            # One round-trip instead of five separate COUNT(*) queries.
            row = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM students WHERE status='active') AS students,
                    (SELECT COUNT(*) FROM teachers) AS teachers,
                    (SELECT COUNT(*) FROM classes) AS classes,
                    (SELECT COUNT(*) FROM parents) AS parents,
                    (SELECT COUNT(*) FROM fee_challans WHERE status!='Paid') AS pending_fees,
                    (SELECT COUNT(*) FROM student_attendance WHERE date=:today AND status='Present') AS present_today
            """, {"today": today()}).fetchone()

            out["stats"] = {
                "students": row["students"], "teachers": row["teachers"],
                "classes": row["classes"], "parents": row["parents"],
                "pending_fees": row["pending_fees"],
            }
            out["today_attendance"] = {"present": row["present_today"], "total": row["students"]}

        elif role == "principal":
            # FR-3.3
            row = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM teacher_attendance WHERE date=:today) AS tatt,
                    (SELECT COUNT(*) FROM students WHERE status='active') AS students,
                    (SELECT COUNT(*) FROM examinations) AS exams,
                    (SELECT COUNT(*) FROM classes) AS classes
            """, {"today": today()}).fetchone()
            out["teacher_attendance_today"] = row["tatt"]
            out["students"] = row["students"]
            out["exams"] = row["exams"]
            out["classes"] = row["classes"]

        elif role == "teacher":
            # FR-3.4: assigned subjects/classes + exam tasks
            t = conn.execute("SELECT * FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
            if t:
                out["assignments"] = [dict(r) for r in conn.execute(
                    "SELECT ta.*, c.name class_name, s.name subject_name FROM teacher_assignments ta "
                    "JOIN classes c ON ta.class_id=c.id JOIN subjects s ON ta.subject_id=s.id "
                    "WHERE ta.teacher_id=?", (t["id"],)).fetchall()]
                out["exams"] = [dict(r) for r in conn.execute(
                    "SELECT e.* FROM examinations e JOIN teacher_assignments ta ON e.class_id=ta.class_id "
                    "WHERE ta.teacher_id=? GROUP BY e.id", (t["id"],)).fetchall()]
            else:
                out["assignments"] = []
                out["exams"] = []
                out["profile_missing"] = True  # teacher user exists but has no linked teacher profile row

        elif role == "class_incharge":
            # FR-3.5: assigned class, student list count, daily attendance
            t = conn.execute("SELECT * FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
            class_id = t["class_id"] if t else None
            out["class_id"] = class_id
            out["needs_setup"] = class_id is None  # flag: not yet assigned to a class

            if class_id:
                row = conn.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM students WHERE class_id=:cid) AS students,
                        (SELECT COUNT(*) FROM student_attendance sa JOIN students s ON sa.student_id=s.id
                         WHERE sa.date=:today AND sa.status='Present' AND s.class_id=:cid) AS present
                """, {"cid": class_id, "today": today()}).fetchone()
                out["students"] = row["students"]
                out["today_attendance"] = {"present": row["present"], "total": row["students"]}
            else:
                out["students"] = 0
                out["today_attendance"] = {"present": 0, "total": 0}

        elif role == "parent":
            # FR-3.6
            sid = session.get("student_id")
            stu = conn.execute(
                "SELECT s.*, c.name class_name, sec.name section_name FROM students s "
                "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
                "WHERE s.id=?", (sid,)).fetchone()
            out["student"] = dict(stu) if stu else None
            out["no_student_linked"] = stu is None

            if stu:
                out["attendance"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM student_attendance WHERE student_id=? ORDER BY date DESC LIMIT 10",
                    (sid,)).fetchall()]
                out["fees"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM fee_challans WHERE student_id=? ORDER BY year DESC, month DESC",
                    (sid,)).fetchall()]
            else:
                out["attendance"] = []
                out["fees"] = []

        else:
            # Unrecognized role (e.g. a role the dashboard hasn't been taught
            # to render yet) — return something explicit rather than a
            # silently near-empty payload.
            out["unsupported_role"] = True

        return out
    finally:
        conn.close()