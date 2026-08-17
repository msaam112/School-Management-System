"""Reports — FR-15. Every report is downloadable as PDF; list endpoints
support in-app viewing. Print is a browser-native action on the PDF."""
import logging
from fastapi import APIRouter, Depends, Response

from app.db import get_conn, today
from app.helpers import get_school, month_name, compute_grade
from app.deps import require_role
from app.main import json_err
from app.pdf import build_generic_report, build_attendance_report, build_result_card, build_fee_challan
from app.ai import generate_result_remark

logger = logging.getLogger("sms.reports")

router = APIRouter(prefix="/api/reports", tags=["reports"])

ADMIN_VIEW = ("super_admin", "principal")
WIDE_VIEW = ("super_admin", "principal", "teacher", "class_incharge")


def _pdf(bytes_, filename):
    return Response(content=bytes_, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _class_incharge_own_class(conn, session):
    """Returns the Class Incharge's own class_id, or None if not applicable/assigned."""
    if session["role"] != "class_incharge":
        return None
    t = conn.execute("SELECT class_id FROM teachers WHERE user_id=?", (session["uid"],)).fetchone()
    return t["class_id"] if t else None


# ------------------------------------------------------------------ Student Reports
@router.get("/students/pdf")
def student_list_pdf(class_id: str = None, session: dict = Depends(require_role(*WIDE_VIEW))):
    conn = get_conn()
    try:
        flt, params = "1=1", []
        own_class = _class_incharge_own_class(conn, session)
        if own_class:
            flt, params = "s.class_id=?", [own_class]
        if class_id:
            flt += " AND s.class_id=?"; params.append(class_id)

        rows = conn.execute(
            "SELECT s.roll_number, s.name, s.gender, c.name class_name, sec.name section_name, s.status "
            "FROM students s LEFT JOIN classes c ON s.class_id=c.id "
            "LEFT JOIN sections sec ON s.section_id=sec.id WHERE " + flt + " ORDER BY s.roll_number",
            params).fetchall()
        data = [[r["roll_number"], r["name"], r["gender"], f"{r['class_name'] or ''} {r['section_name'] or ''}",
                 r["status"]] for r in rows]
        pdf = build_generic_report(get_school(conn), "Student List Report", "",
                                    ["Roll", "Name", "Gender", "Class/Sec", "Status"], data,
                                    [80, 170, 70, 130, 90])
        return _pdf(pdf, "student_list.pdf")
    finally:
        conn.close()


@router.get("/students/{sid}/profile/pdf")
def student_profile_pdf(sid: str, session: dict = Depends(require_role(*WIDE_VIEW, "parent"))):
    conn = get_conn()
    try:
        if session["role"] == "parent" and session.get("student_id") != sid:
            return json_err("Access denied", 403)

        own_class = _class_incharge_own_class(conn, session)
        row = conn.execute(
            "SELECT s.*, c.name class_name, sec.name section_name, p.name parent_name, p.phone parent_phone "
            "FROM students s LEFT JOIN classes c ON s.class_id=c.id "
            "LEFT JOIN sections sec ON s.section_id=sec.id LEFT JOIN parents p ON s.parent_id=p.id "
            "WHERE s.id=?", (sid,)).fetchone()
        if not row:
            return json_err("Student not found", 404)
        if own_class and row["class_id"] != own_class:
            return json_err("Access denied — this student is not in your class", 403)

        data = [[k, v] for k, v in [
            ("Admission ID", row["admission_id"]), ("Roll Number", row["roll_number"]),
            ("Name", row["name"]), ("Gender", row["gender"]), ("Date of Birth", row["dob"]),
            ("Class", f"{row['class_name']} {row['section_name'] or ''}"),
            ("Status", row["status"]), ("Parent", row["parent_name"]), ("Parent Phone", row["parent_phone"]),
        ]]
        pdf = build_generic_report(get_school(conn), "Student Profile", row["name"],
                                    ["Field", "Value"], data, [180, 290])
        return _pdf(pdf, f"student_profile_{row['roll_number']}.pdf")
    finally:
        conn.close()


@router.get("/results/pdf")
def result_report_pdf(exam_id: str, session: dict = Depends(require_role(*WIDE_VIEW))):
    conn = get_conn()
    try:
        exam = conn.execute("SELECT * FROM examinations WHERE id=?", (exam_id,)).fetchone()
        if not exam:
            return json_err("Exam not found", 404)

        own_class = _class_incharge_own_class(conn, session)
        if own_class and exam["class_id"] != own_class:
            return json_err("Access denied — this exam is not for your class", 403)

        rows = conn.execute(
            "SELECT st.roll_number, st.name, s.name subject_name, r.obtained, r.percentage, r.grade, r.pass_fail "
            "FROM results r JOIN students st ON r.student_id=st.id JOIN subjects s ON r.subject_id=s.id "
            "WHERE r.exam_id=? ORDER BY st.roll_number", (exam_id,)).fetchall()
        data = [[r["roll_number"], r["name"], r["subject_name"], r["obtained"],
                 f"{r['percentage']:.1f}%", r["grade"], r["pass_fail"]] for r in rows]
        pdf = build_generic_report(get_school(conn), "Result Report", exam["name"],
                                    ["Roll", "Name", "Subject", "Obtained", "%", "Grade", "Result"], data,
                                    [60, 130, 100, 60, 55, 55, 60])
        return _pdf(pdf, f"result_report_{exam_id}.pdf")
    finally:
        conn.close()


@router.get("/promotions/pdf")
def promotion_report_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT p.academic_year, s.name student_name, s.roll_number, c1.name from_name, "
            "c2.name to_name, p.status FROM promotions p JOIN students s ON p.student_id=s.id "
            "LEFT JOIN classes c1 ON p.from_class=c1.id LEFT JOIN classes c2 ON p.to_class=c2.id "
            "ORDER BY p.promoted_at DESC").fetchall()
        data = [[r["academic_year"], r["roll_number"], r["student_name"], r["from_name"],
                 r["to_name"], r["status"]] for r in rows]
        pdf = build_generic_report(get_school(conn), "Promotion Report", "",
                                    ["Year", "Roll", "Student", "From", "To", "Status"], data,
                                    [60, 70, 150, 80, 80, 80])
        return _pdf(pdf, "promotion_report.pdf")
    finally:
        conn.close()


# ------------------------------------------------------------------ Teacher Reports
@router.get("/teachers/pdf")
def teacher_list_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT employee_id, name, email, qualification, employment_status FROM teachers ORDER BY name"
        ).fetchall()
        data = [[r["employee_id"], r["name"], r["email"], r["qualification"], r["employment_status"]]
                for r in rows]
        pdf = build_generic_report(get_school(conn), "Teacher List Report", "",
                                    ["Emp ID", "Name", "Email", "Qualification", "Status"], data,
                                    [80, 130, 160, 100, 70])
        return _pdf(pdf, "teacher_list.pdf")
    finally:
        conn.close()


@router.get("/teacher-assignments/pdf")
def teacher_assignment_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT t.name teacher_name, c.name class_name, s.name subject_name FROM teacher_assignments ta "
            "JOIN teachers t ON ta.teacher_id=t.id JOIN classes c ON ta.class_id=c.id "
            "JOIN subjects s ON ta.subject_id=s.id ORDER BY t.name").fetchall()
        data = [[r["teacher_name"], r["class_name"], r["subject_name"]] for r in rows]
        pdf = build_generic_report(get_school(conn), "Teacher Assignment Report", "",
                                    ["Teacher", "Class", "Subject"], data, [180, 150, 150])
        return _pdf(pdf, "teacher_assignments.pdf")
    finally:
        conn.close()


# ------------------------------------------------------------------ Attendance Reports
@router.get("/attendance/student/pdf")
def student_attendance_pdf(class_id: str, section_id: str = None, date: str = None,
                            session: dict = Depends(require_role(*WIDE_VIEW))):
    conn = get_conn()
    try:
        own_class = _class_incharge_own_class(conn, session)
        if own_class and class_id != own_class:
            return json_err("Access denied — you may only view attendance for your own class", 403)

        d = date or today()
        cls = conn.execute("SELECT name FROM classes WHERE id=?", (class_id,)).fetchone()
        secn = conn.execute("SELECT name FROM sections WHERE id=?", (section_id,)).fetchone() if section_id else None

        rows = conn.execute(
            "SELECT s.roll_number, s.name, COALESCE(sa.status,'-') status FROM students s "
            "LEFT JOIN student_attendance sa ON sa.student_id=s.id AND sa.date=? WHERE s.class_id=?" +
            (" AND s.section_id=?" if section_id else "") + " ORDER BY s.roll_number",
            (d, class_id) + ((section_id,) if section_id else ())).fetchall()

        data = [{"roll": r["roll_number"], "name": r["name"], "status": r["status"]} for r in rows]
        summary = {"total": len(data), "present": 0, "absent": 0, "leave": 0}
        for r in data:
            if r["status"] == "Present": summary["present"] += 1
            elif r["status"] == "Absent": summary["absent"] += 1
            elif r["status"] == "Leave": summary["leave"] += 1

        pdf = build_attendance_report(get_school(conn), d, cls["name"] if cls else "",
                                       secn["name"] if secn else "All", data, summary)
        return _pdf(pdf, f"attendance_{class_id}_{d}.pdf")
    finally:
        conn.close()


@router.get("/attendance/teacher/pdf")
def teacher_attendance_pdf(date: str = None, session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        d = date or today()
        rows = conn.execute(
            "SELECT t.employee_id, t.name, COALESCE(ta.status,'-') status FROM teachers t "
            "LEFT JOIN teacher_attendance ta ON ta.teacher_id=t.id AND ta.date=? ORDER BY t.name",
            (d,)).fetchall()
        data = [{"roll": r["employee_id"], "name": r["name"], "status": r["status"]} for r in rows]
        summary = {"total": len(data), "present": 0, "absent": 0, "leave": 0}
        for r in data:
            if r["status"] == "Present": summary["present"] += 1
            elif r["status"] == "Absent": summary["absent"] += 1
            elif r["status"] == "Leave": summary["leave"] += 1

        pdf = build_attendance_report(get_school(conn), d, "All Teachers", "Staff", data, summary)
        return _pdf(pdf, f"teacher_attendance_{d}.pdf")
    finally:
        conn.close()


@router.get("/attendance-summary/pdf")
def attendance_summary_pdf(date: str = None, session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        d = date or today()
        rows = conn.execute(
            "SELECT c.name class_name, COUNT(s.id) total, "
            "SUM(CASE WHEN sa.status='Present' THEN 1 ELSE 0 END) present, "
            "SUM(CASE WHEN sa.status='Absent' THEN 1 ELSE 0 END) absent, "
            "SUM(CASE WHEN sa.status='Leave' THEN 1 ELSE 0 END) leave FROM classes c "
            "LEFT JOIN students s ON s.class_id=c.id "
            "LEFT JOIN student_attendance sa ON sa.student_id=s.id AND sa.date=? "
            "GROUP BY c.id ORDER BY c.name", (d,)).fetchall()
        data = [[r["class_name"], r["total"] or 0, r["present"] or 0, r["absent"] or 0, r["leave"] or 0]
                for r in rows]
        pdf = build_generic_report(get_school(conn), "Attendance Summary", f"Date: {d}",
                                    ["Class", "Total", "Present", "Absent", "Leave"], data,
                                    [150, 90, 90, 90, 90])
        return _pdf(pdf, f"attendance_summary_{d}.pdf")
    finally:
        conn.close()


@router.get("/class-wise/pdf")
def class_wise_report_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT c.name class_name, "
            "(SELECT COUNT(*) FROM sections WHERE class_id=c.id) sections, "
            "(SELECT COUNT(*) FROM students WHERE class_id=c.id AND status='active') students "
            "FROM classes c ORDER BY c.name").fetchall()
        data = [[r["class_name"], r["sections"], r["students"]] for r in rows]
        pdf = build_generic_report(get_school(conn), "Class-wise Report", "",
                                    ["Class", "Sections", "Active Students"], data, [200, 140, 140])
        return _pdf(pdf, "class_wise_report.pdf")
    finally:
        conn.close()


@router.get("/dashboard-stats/pdf")
def dashboard_stats_pdf(session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        stats = {
            "Total Students": conn.execute("SELECT COUNT(*) c FROM students WHERE status='active'").fetchone()["c"],
            "Total Teachers": conn.execute("SELECT COUNT(*) c FROM teachers").fetchone()["c"],
            "Total Classes": conn.execute("SELECT COUNT(*) c FROM classes").fetchone()["c"],
            "Total Parents": conn.execute("SELECT COUNT(*) c FROM parents").fetchone()["c"],
            "Pending Fee Challans": conn.execute(
                "SELECT COUNT(*) c FROM fee_challans WHERE status!='Paid'").fetchone()["c"],
        }
        data = [[k, v] for k, v in stats.items()]
        pdf = build_generic_report(get_school(conn), "Dashboard Statistics", "", ["Metric", "Value"], data,
                                    [280, 190])
        return _pdf(pdf, "dashboard_stats.pdf")
    finally:
        conn.close()


# ------------------------------------------------------------------ Fee Reports
@router.get("/fees/paid/pdf")
def paid_fee_report_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    return _fee_status_report("Paid", "Paid Fee Report")


@router.get("/fees/unpaid/pdf")
def unpaid_fee_report_pdf(session: dict = Depends(require_role(*ADMIN_VIEW))):
    return _fee_status_report("Unpaid", "Unpaid Fee Report")


def _fee_status_report(status: str, title: str):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT fc.month, fc.year, s.roll_number, s.name student_name, c.name class_name, "
            "fc.total, fc.amount_paid "
            "FROM fee_challans fc JOIN students s ON fc.student_id=s.id "
            "LEFT JOIN classes c ON s.class_id=c.id WHERE fc.status=? ORDER BY fc.year, fc.month",
            (status,)).fetchall()
        data = [[month_name(r["month"]) + f" {r['year']}", r["roll_number"], r["student_name"],
                 r["class_name"], f"Rs. {r['total']:.0f}"] for r in rows]
        pdf = build_generic_report(get_school(conn), title, "", ["Period", "Roll", "Student", "Class", "Amount"],
                                    data, [90, 70, 140, 100, 90])
        return _pdf(pdf, f"{status.lower()}_fee_report.pdf")
    finally:
        conn.close()


@router.get("/fees/collection/pdf")
def monthly_collection_pdf(month: int = None, year: int = None,
                            session: dict = Depends(require_role(*ADMIN_VIEW))):
    conn = get_conn()
    try:
        sql = ("SELECT fc.month, fc.year, SUM(fc.total) total, "
               "SUM(fc.amount_paid) collected, COUNT(*) count "
               "FROM fee_challans fc WHERE 1=1")
        params = []
        if month: sql += " AND fc.month=?"; params.append(month)
        if year: sql += " AND fc.year=?"; params.append(year)
        sql += " GROUP BY fc.year, fc.month ORDER BY fc.year, fc.month"
        rows = conn.execute(sql, params).fetchall()
        data = [[month_name(r["month"]) + f" {r['year']}", r["count"], f"Rs. {r['total']:.0f}",
                 f"Rs. {r['collected'] or 0:.0f}"] for r in rows]
        pdf = build_generic_report(get_school(conn), "Monthly Collection Report", "",
                                    ["Month", "Challans", "Total Billed", "Collected"], data,
                                    [130, 90, 130, 130])
        return _pdf(pdf, "monthly_collection.pdf")
    finally:
        conn.close()


@router.get("/fees/challan/{chid}/pdf")
def fee_challan_pdf(chid: str, session: dict = Depends(require_role(*ADMIN_VIEW, "parent"))):
    conn = get_conn()
    try:
        ch = conn.execute("SELECT * FROM fee_challans WHERE id=?", (chid,)).fetchone()
        if not ch:
            return json_err("Challan not found", 404)
        if session["role"] == "parent" and ch["student_id"] != session.get("student_id"):
            return json_err("Access denied", 403)

        student = conn.execute(
            "SELECT s.*, c.name class_name, sec.name section_name FROM students s "
            "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
            "WHERE s.id=?", (ch["student_id"],)).fetchone()
        fs = conn.execute(
            "SELECT fs.* FROM students s JOIN fee_structures fs ON s.class_id=fs.class_id WHERE s.id=?",
            (ch["student_id"],)).fetchone()

        # NOTE: this breakdown is a best-effort reconstruction from the
        # CURRENT fee structure — it is informational, and may not exactly
        # match the challan's stored `total` if manual charges were added,
        # or if the fee structure changed after this challan was generated.
        # The challan's stored `total` (and amount_paid) remain the actual
        # source of truth.
        breakdown = []
        if fs:
            has_prev = conn.execute(
                "SELECT COUNT(*) c FROM fee_challans WHERE student_id=? AND id!=? AND issue_date<?",
                (ch["student_id"], chid, ch["issue_date"])).fetchone()["c"]
            if has_prev == 0 and fs["admission_fee"]:
                breakdown.append({"label": "Admission Fee", "amount": fs["admission_fee"]})
            breakdown.append({"label": "Tuition Fee", "amount": fs["tuition_fee"]})
            if fs["exam_fee"]:
                breakdown.append({"label": "Examination Fee", "amount": fs["exam_fee"]})
            if fs["custom_fee"]:
                breakdown.append({"label": fs["custom_name"] or "Custom Fee", "amount": fs["custom_fee"]})

        manual = [dict(r) for r in conn.execute(
            "SELECT * FROM manual_fees WHERE challan_id=?", (chid,)).fetchall()]

        pdf = build_fee_challan(get_school(conn), dict(student), dict(ch), breakdown, manual, ch["total"])
        return _pdf(pdf, f"challan_{chid}.pdf")
    finally:
        conn.close()


# ------------------------------------------------------------------ Result Card
@router.get("/results/card/pdf")
def result_card_pdf(student_id: str, exam_id: str,
                     session: dict = Depends(require_role(*WIDE_VIEW, "parent"))):
    if session["role"] == "parent" and session.get("student_id") != student_id:
        return json_err("Access denied", 403)

    conn = get_conn()
    try:
        own_class = _class_incharge_own_class(conn, session)

        student = conn.execute(
            "SELECT s.*, c.name class_name, sec.name section_name FROM students s "
            "LEFT JOIN classes c ON s.class_id=c.id LEFT JOIN sections sec ON s.section_id=sec.id "
            "WHERE s.id=?", (student_id,)).fetchone()
        exam = conn.execute("SELECT * FROM examinations WHERE id=?", (exam_id,)).fetchone()
        if not student or not exam:
            return json_err("Student or exam not found", 404)
        if own_class and student["class_id"] != own_class:
            return json_err("Access denied — this student is not in your class", 403)

        rows = conn.execute(
            "SELECT r.*, s.name subject_name FROM results r JOIN subjects s ON r.subject_id=s.id "
            "WHERE r.student_id=? AND r.exam_id=?", (student_id, exam_id)).fetchall()
        subject_rows = [{"subject": r["subject_name"], "obtained": r["obtained"], "total": r["total"],
                          "percentage": r["percentage"], "grade": r["grade"], "pass_fail": r["pass_fail"]}
                         for r in rows]
        if not subject_rows:
            return json_err("No results found for this student/exam", 404)

        tot_obt = sum(r["obtained"] for r in rows)
        tot_tot = sum(r["total"] for r in rows) or 1
        pct = tot_obt / tot_tot * 100
        all_pass = all(r["pass_fail"] == "Pass" for r in rows)
        totals = {"obtained": tot_obt, "total": tot_tot, "percentage": round(pct, 2),
                  "grade": compute_grade(pct), "pass_fail": "Pass" if all_pass else "Fail"}

        try:
            totals["remark"] = generate_result_remark(student["name"], exam["name"], subject_rows,
                                                        totals["percentage"], totals["pass_fail"])
        except Exception:
            logger.exception("AI remark generation failed for result card: student=%s exam=%s",
                              student_id, exam_id)
            totals["remark"] = None  # AI is best-effort; PDF still generates without it

        pdf = build_result_card(get_school(conn), dict(student), dict(exam), subject_rows, totals)
        return _pdf(pdf, f"result_{student['roll_number']}_{exam_id}.pdf")
    finally:
        conn.close()