"""Teacher-Class-Subject Assignments — FR-6.3, FR-8."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db import get_conn
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/assignments", tags=["assignments"])

VIEW_ROLES = ("super_admin", "principal", "teacher", "class_incharge")


class AssignmentCreate(BaseModel):
    teacher_id: str
    class_id: str
    subject_id: str


@router.get("")
def list_assignments(session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT ta.*, t.name teacher_name, c.name class_name, s.name subject_name "
            "FROM teacher_assignments ta "
            "JOIN teachers t ON ta.teacher_id=t.id "
            "JOIN classes c ON ta.class_id=c.id "
            "JOIN subjects s ON ta.subject_id=s.id "
            "ORDER BY c.name, s.name").fetchall()
        return {"assignments": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_assignment(body: AssignmentCreate, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        t = conn.execute("SELECT id, name FROM teachers WHERE id=?", (body.teacher_id,)).fetchone()
        if not t:
            return json_err("Teacher not found", 404)
        c = conn.execute("SELECT id, name FROM classes WHERE id=?", (body.class_id,)).fetchone()
        if not c:
            return json_err("Class not found", 404)
        s = conn.execute("SELECT id, name FROM subjects WHERE id=?", (body.subject_id,)).fetchone()
        if not s:
            return json_err("Subject not found", 404)

        dup = conn.execute(
            "SELECT id FROM teacher_assignments WHERE teacher_id=? AND class_id=? AND subject_id=?",
            (body.teacher_id, body.class_id, body.subject_id)).fetchone()
        if dup:
            return json_err("This teacher is already assigned to this class and subject", 400)

        aid = new_id("asg")
        conn.execute(
            "INSERT INTO teacher_assignments (id, teacher_id, class_id, subject_id) VALUES (?,?,?,?)",
            (aid, body.teacher_id, body.class_id, body.subject_id))

        audit(session, "Assignments", "Create",
              f"Assigned {t['name']} to {c['name']} / {s['name']}",
              conn=conn)
        conn.commit()
        return {"id": aid}
    finally:
        conn.close()


@router.delete("/{aid}")
def delete_assignment(aid: str, session: dict = Depends(require_role("super_admin"))):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT ta.*, t.name teacher_name, c.name class_name, s.name subject_name "
            "FROM teacher_assignments ta "
            "JOIN teachers t ON ta.teacher_id=t.id "
            "JOIN classes c ON ta.class_id=c.id "
            "JOIN subjects s ON ta.subject_id=s.id "
            "WHERE ta.id=?", (aid,)).fetchone()
        if not existing:
            return json_err("Assignment not found", 404)

        # Check for existing exam results tied to this class/subject combo —
        # removing the assignment doesn't delete them, but it's worth
        # surfacing so the admin isn't surprised by orphaned-looking data.
        results_count = conn.execute(
            "SELECT COUNT(*) c FROM results WHERE subject_id=? AND student_id IN "
            "(SELECT id FROM students WHERE class_id=?)",
            (existing["subject_id"], existing["class_id"])).fetchone()["c"]

        conn.execute("DELETE FROM teacher_assignments WHERE id=?", (aid,))
        audit(session, "Assignments", "Delete",
              f"Removed {existing['teacher_name']} from {existing['class_name']} / {existing['subject_name']}",
              conn=conn)
        conn.commit()

        response = {"message": "Assignment removed"}
        if results_count:
            response["warning"] = (
                f"This class/subject already has {results_count} recorded exam result(s). "
                "They remain in the system but won't be editable through the normal marks-entry "
                "flow until a teacher is reassigned to this subject for this class."
            )
        return response
    finally:
        conn.close()