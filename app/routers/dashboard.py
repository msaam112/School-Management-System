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
            # FR-3.2: totals + today's attendance + pending fees
            out["stats"] = {
                "students": conn.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"],
                "teachers": conn.execute("SELECT COUNT(*) c FROM teachers").fetchone()["c"],
                "classes": conn.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"],
                "parents": conn.execute("SELECT COUNT(*) c FROM parents").fetchone()["c"],
                "pending_fees": conn.execute(
                    "SELECT COUNT(*) c FROM fee_challans WHERE status!='Paid'").fetchone()["c"],
            }
            present = conn.execute(
                "SELECT COUNT(*) c FROM student_attendance WHERE date=? AND status='Present'",
                (today(),)).fetchone()["c"]
            total = conn.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"]
            out["today_attendance"] = {"present": present, "total": total}

        elif role == "principal":
            # FR-3.3
            out["teacher_attendance_today"] = conn.execute(
                "SELECT COUNT(*) c FROM teacher_attendance WHERE date=?", (today(),)).fetchone()["c"]
            out["students"] = conn.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"]
            out["exams"] = conn.execute("SELECT COUNT(*) c FROM examinations").fetchone()["c"]
            out["classes"] = conn.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"]

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

        elif role == "class_incharge":
            # FR-3.5: assigned class, student list count, daily attendance
            t = conn.execute("SELECT * FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
            class_id = t["class_id"] if t else None
            out["class_id"] = class_id
            out["students"] = conn.execute(
                "SELECT COUNT(*) c FROM students WHERE class_id=?", (class_id,)).fetchone()["c"] if class_id else 0
            present = conn.execute(
                "SELECT COUNT(*) c FROM student_attendance sa JOIN students s ON sa.student_id=s.id "
                "WHERE sa.date=? AND sa.status='Present' AND s.class_id=?",
                (today(), class_id)).fetchone()["c"] if class_id else 0
            out["today_attendance"] = {"present": present, "total": out["students"]}

        elif role == "parent":
            # FR-3.6
            sid = session.get("student_id")
            stu = conn.execute(
                "SELECT s.*, c.name class_name, sec.name section_name FROM students s "
                "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
                "WHERE s.id=?", (sid,)).fetchone()
            out["student"] = dict(stu) if stu else None
            out["attendance"] = [dict(r) for r in conn.execute(
                "SELECT * FROM student_attendance WHERE student_id=? ORDER BY date DESC LIMIT 10",
                (sid,)).fetchall()]
            out["fees"] = [dict(r) for r in conn.execute(
                "SELECT * FROM fee_challans WHERE student_id=? ORDER BY year DESC, month DESC",
                (sid,)).fetchall()]

        return out
    finally:
        conn.close()