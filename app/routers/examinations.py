"""Examinations & Results — FR-11, FR-12, UC-6."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.db import get_conn
from app.security import new_id
from app.helpers import audit, compute_grade, compute_pass_fail
from app.ai import generate_result_remark
from app.deps import require_role
from app.main import json_err

logger = logging.getLogger("sms.examinations")

router = APIRouter(prefix="/api", tags=["examinations"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge", "parent")
CREATE_ROLES = ("super_admin", "principal", "teacher", "class_incharge")
MARKS_ROLES = ("super_admin", "principal", "teacher", "class_incharge")


class ExamCreate(BaseModel):
    name: str
    exam_date: Optional[str] = None
    class_id: str
    section_id: Optional[str] = None


class MarkEntry(BaseModel):
    student_id: str
    obtained: float
    total: Optional[float] = 100


class MarksSubmit(BaseModel):
    subject_id: str
    marks: List[MarkEntry]


# ------------------------------------------------------------------ exams
@router.get("/exams")
def list_exams(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT e.*, c.name class_name, sec.name section_name FROM examinations e "
            "LEFT JOIN classes c ON e.class_id=c.id LEFT JOIN sections sec ON e.section_id=sec.id "
            "ORDER BY e.exam_date DESC").fetchall()
        return {"exams": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/exams")
def create_exam(body: ExamCreate, session: dict = Depends(require_role(*CREATE_ROLES))):
    name = body.name.strip()
    if not name:
        return json_err("Exam name is required", 400)

    conn = get_conn()
    try:
        cls = conn.execute("SELECT id FROM classes WHERE id=?", (body.class_id,)).fetchone()
        if not cls:
            return json_err("Class not found", 404)

        eid = new_id("exam")
        conn.execute(
            "INSERT INTO examinations (id, name, exam_date, class_id, section_id, created_by) "
            "VALUES (?,?,?,?,?,?)",
            (eid, name, body.exam_date, body.class_id, body.section_id, session.get("uid")))
        audit(session, "Exams", "Create", f"Created exam {name}", conn=conn)
        conn.commit()
        return {"id": eid}
    finally:
        conn.close()


@router.get("/exams/{eid}")
def exam_detail(eid: str, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        exam = conn.execute("SELECT * FROM examinations WHERE id=?", (eid,)).fetchone()
        if not exam:
            return json_err("Exam not found", 404)

        students = conn.execute(
            "SELECT id, roll_number, name FROM students WHERE class_id=?" +
            (" AND section_id=?" if exam["section_id"] else "") + " ORDER BY roll_number",
            (exam["class_id"],) + ((exam["section_id"],) if exam["section_id"] else ())).fetchall()

        subjects = conn.execute(
            "SELECT DISTINCT s.* FROM subjects s JOIN teacher_assignments ta ON ta.subject_id=s.id "
            "WHERE ta.class_id=?", (exam["class_id"],)).fetchall()

        return {"exam": dict(exam), "students": [dict(r) for r in students],
                "subjects": [dict(r) for r in subjects]}
    finally:
        conn.close()


@router.delete("/exams/{eid}")
def delete_exam(eid: str, session: dict = Depends(require_role("super_admin", "principal"))):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM examinations WHERE id=?", (eid,)).fetchone()
        if not existing:
            return json_err("Exam not found", 404)

        conn.execute("DELETE FROM results WHERE exam_id=?", (eid,))
        conn.execute("DELETE FROM examinations WHERE id=?", (eid,))
        audit(session, "Exams", "Delete", f"Removed exam '{existing['name']}' and its results", conn=conn)
        conn.commit()
        return {"message": "Exam removed"}
    finally:
        conn.close()


# ------------------------------------------------------------------ marks / results
@router.post("/exams/{eid}/marks")
def enter_marks(eid: str, body: MarksSubmit, session: dict = Depends(require_role(*MARKS_ROLES))):
    conn = get_conn()
    try:
        exam = conn.execute("SELECT * FROM examinations WHERE id=?", (eid,)).fetchone()
        if not exam:
            return json_err("Exam not found", 404)

        subject = conn.execute("SELECT id FROM subjects WHERE id=?", (body.subject_id,)).fetchone()
        if not subject:
            return json_err("Subject not found", 404)

        if not body.marks:
            return json_err("At least one mark entry is required", 400)

        # Validate every entry up front, before writing anything — reject the
        # whole submission on bad data instead of silently skipping/corrupting.
        for m in body.marks:
            total = m.total or 100
            if total <= 0:
                return json_err(f"Total marks must be greater than zero (student {m.student_id})", 400)
            if m.obtained < 0:
                return json_err(f"Obtained marks cannot be negative (student {m.student_id})", 400)
            if m.obtained > total:
                return json_err(
                    f"Obtained marks ({m.obtained}) cannot exceed total marks ({total}) for student {m.student_id}",
                    400
                )

        # Validate every submitted student actually belongs to this exam's class/section.
        student_ids = [m.student_id for m in body.marks]
        placeholders = ",".join("?" * len(student_ids))
        sql = f"SELECT id FROM students WHERE id IN ({placeholders}) AND class_id=?"
        params = student_ids + [exam["class_id"]]
        if exam["section_id"]:
            sql += " AND section_id=?"
            params.append(exam["section_id"])
        valid_ids = {r["id"] for r in conn.execute(sql, params).fetchall()}
        invalid_ids = set(student_ids) - valid_ids
        if invalid_ids:
            return json_err(f"{len(invalid_ids)} student(s) in this submission are not in this exam's class.", 400)

        for m in body.marks:
            total = m.total or 100
            pct = (m.obtained / total) * 100
            grade = compute_grade(pct)
            pf = compute_pass_fail(pct, conn=conn)  # reads the school's configured pass mark
            conn.execute(
                "INSERT INTO results (id, student_id, exam_id, subject_id, obtained, total, "
                "percentage, grade, pass_fail) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(student_id, exam_id, subject_id) DO UPDATE SET "
                "obtained=excluded.obtained, total=excluded.total, percentage=excluded.percentage, "
                "grade=excluded.grade, pass_fail=excluded.pass_fail",
                (new_id("res"), m.student_id, eid, body.subject_id, m.obtained, total,
                 round(pct, 2), grade, pf))

        audit(session, "Results", "Enter Marks",
              f"Entered marks for exam '{exam['name']}' subject {body.subject_id}", conn=conn)
        conn.commit()
        return {"message": "Marks saved"}
    finally:
        conn.close()


@router.get("/exams/{eid}/results")
def exam_results(eid: str, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT r.*, s.name subject_name, st.name student_name, st.roll_number FROM results r "
            "JOIN subjects s ON r.subject_id=s.id JOIN students st ON r.student_id=st.id "
            "WHERE r.exam_id=? ORDER BY st.roll_number", (eid,)).fetchall()
        return {"results": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/results/student")
def student_results(student_id: str, exam_id: str = None,
                     session: dict = Depends(require_role(*VIEW_ROLES))):
    if session["role"] == "parent" and session.get("student_id") != student_id:
        return json_err("Access denied", 403)

    conn = get_conn()
    try:
        sql = ("SELECT r.*, e.name exam_name, s.name subject_name FROM results r "
               "JOIN examinations e ON r.exam_id=e.id JOIN subjects s ON r.subject_id=s.id "
               "WHERE r.student_id=?")
        params = [student_id]
        if exam_id:
            sql += " AND r.exam_id=?"
            params.append(exam_id)
        sql += " ORDER BY e.exam_date DESC, s.name"
        rows = conn.execute(sql, params).fetchall()
        return {"results": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/results/remark")
def get_result_remark(student_id: str, exam_id: str,
                       session: dict = Depends(require_role(*VIEW_ROLES))):
    if session["role"] == "parent" and session.get("student_id") != student_id:
        return json_err("Access denied", 403)

    conn = get_conn()
    try:
        student = conn.execute("SELECT name FROM students WHERE id=?", (student_id,)).fetchone()
        exam = conn.execute("SELECT name FROM examinations WHERE id=?", (exam_id,)).fetchone()
        if not student or not exam:
            return json_err("Student or exam not found", 404)

        rows = conn.execute(
            "SELECT r.*, s.name subject_name FROM results r JOIN subjects s ON r.subject_id=s.id "
            "WHERE r.student_id=? AND r.exam_id=?", (student_id, exam_id)).fetchall()
        if not rows:
            return json_err("No results found for this student/exam", 404)

        subject_rows = [{"subject": r["subject_name"], "obtained": r["obtained"], "total": r["total"],
                          "percentage": r["percentage"], "grade": r["grade"], "pass_fail": r["pass_fail"]}
                         for r in rows]
        tot_obt = sum(r["obtained"] for r in rows)
        tot_tot = sum(r["total"] for r in rows) or 1
        pct = tot_obt / tot_tot * 100
        overall_result = "Pass" if all(r["pass_fail"] == "Pass" for r in rows) else "Fail"

        try:
            remark = generate_result_remark(student["name"], exam["name"], subject_rows, pct, overall_result)
        except Exception:
            logger.exception("AI remark generation failed for student=%s exam=%s", student_id, exam_id)
            return json_err("Could not generate a remark right now. Please try again shortly.", 502)

        return {"remark": remark}
    finally:
        conn.close()