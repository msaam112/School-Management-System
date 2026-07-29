"""Student Promotion — FR-13, BR (end-of-year processing).

Eligibility rule: a student is eligible for promotion if their most recent
examination for their current class has no 'Fail' results. Super Admin or
Principal may override this per-student to force a promotion anyway; if not
overridden and the student failed, they are recorded as 'Retained' (their
class does not change) rather than silently skipped.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
import datetime

from app.db import get_conn, now_iso
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api", tags=["promotions"])


class PromotionItem(BaseModel):
    student_id: str
    to_class_id: str
    override: Optional[bool] = False


class PromoteRequest(BaseModel):
    academic_year: Optional[str] = None
    promotions: List[PromotionItem]


def _is_eligible(conn, student_id: str, class_id: str) -> bool:
    """True if the student's most recent exam for this class has no Fail results.
    A student with no exam results at all is treated as eligible (nothing to fail)."""
    latest_exam = conn.execute(
        "SELECT id FROM examinations WHERE class_id=? "
        "AND id IN (SELECT DISTINCT exam_id FROM results WHERE student_id=?) "
        "ORDER BY exam_date DESC LIMIT 1", (class_id, student_id)).fetchone()
    if not latest_exam:
        return True
    fail_count = conn.execute(
        "SELECT COUNT(*) c FROM results WHERE student_id=? AND exam_id=? AND pass_fail='Fail'",
        (student_id, latest_exam["id"])).fetchone()["c"]
    return fail_count == 0


@router.post("/promote")
def promote(body: PromoteRequest, session: dict = Depends(require_role("super_admin", "principal"))):
    if not body.promotions:
        return json_err("No students provided for promotion", 400)

    year = body.academic_year or str(datetime.date.today().year)
    conn = get_conn()
    try:
        promoted, retained = 0, 0
        for item in body.promotions:
            stu = conn.execute("SELECT * FROM students WHERE id=?", (item.student_id,)).fetchone()
            if not stu:
                continue

            eligible = _is_eligible(conn, item.student_id, stu["class_id"])
            will_promote = eligible or item.override

            from_class = stu["class_id"]
            to_class = item.to_class_id if will_promote else from_class
            status = "Promoted" if will_promote else "Retained"

            if will_promote:
                conn.execute("UPDATE students SET class_id=? WHERE id=?", (to_class, item.student_id))
                promoted += 1
            else:
                retained += 1

            conn.execute(
                "INSERT INTO promotions (id, student_id, from_class, to_class, academic_year, "
                "status, promoted_by, promoted_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_id("prm"), item.student_id, from_class, to_class, year, status,
                 session.get("uid"), now_iso()))

        audit(session, "Promotion", "Promote",
              f"Processed {len(body.promotions)} students for {year}: "
              f"{promoted} promoted, {retained} retained", conn=conn)
        conn.commit()
        return {"message": f"{promoted} promoted, {retained} retained",
                "promoted": promoted, "retained": retained}
    finally:
        conn.close()


@router.get("/promotions")
def list_promotions(session: dict = Depends(require_role("super_admin", "principal"))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT p.*, s.name student_name, c1.name from_name, c2.name to_name FROM promotions p "
            "JOIN students s ON p.student_id=s.id "
            "LEFT JOIN classes c1 ON p.from_class=c1.id "
            "LEFT JOIN classes c2 ON p.to_class=c2.id "
            "ORDER BY p.promoted_at DESC").fetchall()
        return {"promotions": [dict(r) for r in rows]}
    finally:
        conn.close()