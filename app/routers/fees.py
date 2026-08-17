"""Fee Challans — FR-14.2, FR-14.3, FR-14.4, FR-14.5, UC-7."""
import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.config import PAYMENT_STATUSES
from app.db import get_conn, today, now_iso
from app.security import new_id
from app.helpers import audit
from app.deps import require_role
from app.main import json_err

router = APIRouter(prefix="/api/fees", tags=["fees"])

VIEW_ROLES = ("super_admin", "principal", "parent")
KNOWN_CHARGE_TYPES = {"fine", "transport", "library", "extra exam", "custom"}


class GenerateRequest(BaseModel):
    month: Optional[int] = None
    year: Optional[int] = None
    class_id: Optional[str] = None


class ManualChargeCreate(BaseModel):
    charge_type: str
    description: Optional[str] = None
    amount: float


class PayRequest(BaseModel):
    status: str
    amount_paid: Optional[float] = None  # required when status == "Partially Paid"


def _derive_status(total: float, amount_paid: float) -> str:
    if amount_paid <= 0:
        return "Unpaid"
    if amount_paid >= total:
        return "Paid"
    return "Partially Paid"


@router.post("/generate")
def generate_challans(body: GenerateRequest, session: dict = Depends(require_role("super_admin"))):
    month = body.month or datetime.date.today().month
    year = body.year or datetime.date.today().year

    if not (1 <= month <= 12):
        return json_err("Month must be between 1 and 12", 400)
    if not (2000 <= year <= 2100):
        return json_err("Year must be a realistic value", 400)

    conn = get_conn()
    try:
        sql = ("SELECT s.id student_id, fs.admission_fee, fs.tuition_fee, fs.exam_fee, fs.custom_fee "
               "FROM students s JOIN fee_structures fs ON s.class_id=fs.class_id "
               "WHERE s.status='active'" + (" AND s.class_id=?" if body.class_id else ""))
        params = (body.class_id,) if body.class_id else ()
        students = conn.execute(sql, params).fetchall()

        generated = 0
        for st in students:
            existing = conn.execute(
                "SELECT id FROM fee_challans WHERE student_id=? AND month=? AND year=?",
                (st["student_id"], month, year)).fetchone()
            if existing:
                continue

            has_prev = conn.execute(
                "SELECT COUNT(*) c FROM fee_challans WHERE student_id=?", (st["student_id"],)).fetchone()["c"]
            admission = st["admission_fee"] if has_prev == 0 else 0
            total = admission + st["tuition_fee"] + st["exam_fee"] + (st["custom_fee"] or 0)

            issue = today()
            due = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

            chid = new_id("chg")
            conn.execute(
                "INSERT INTO fee_challans (id, student_id, month, year, issue_date, due_date, total, "
                "amount_paid, status) VALUES (?,?,?,?,?,?,?,0,?)",
                (chid, st["student_id"], month, year, issue, due, total, "Unpaid"))
            generated += 1

        audit(session, "Fees", "Generate", f"Generated {generated} challans for {month}/{year}", conn=conn)
        conn.commit()
        return {"message": f"{generated} challans generated", "count": generated}
    finally:
        conn.close()


@router.get("/challans")
def list_challans(status: str = None, month: int = None, year: int = None,
                   session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        flt, params = "1=1", []
        if session["role"] == "parent":
            flt, params = "fc.student_id=?", [session.get("student_id")]

        sql = ("SELECT fc.*, s.name student_name, s.roll_number, c.name class_name FROM fee_challans fc "
               "JOIN students s ON fc.student_id=s.id LEFT JOIN classes c ON s.class_id=c.id WHERE " + flt)
        if status:
            sql += " AND fc.status=?"; params.append(status)
        if month:
            sql += " AND fc.month=?"; params.append(month)
        if year:
            sql += " AND fc.year=?"; params.append(year)
        sql += " ORDER BY fc.year DESC, fc.month DESC"

        rows = conn.execute(sql, params).fetchall()
        return {"challans": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/challan/{chid}")
def challan_detail(chid: str, session: dict = Depends(require_role(*VIEW_ROLES))):
    conn = get_conn()
    try:
        ch = conn.execute("SELECT * FROM fee_challans WHERE id=?", (chid,)).fetchone()
        if not ch:
            return json_err("Challan not found", 404)
        if session["role"] == "parent" and ch["student_id"] != session.get("student_id"):
            return json_err("Access denied", 403)

        manual = conn.execute("SELECT * FROM manual_fees WHERE challan_id=?", (chid,)).fetchall()
        return {"challan": dict(ch), "manual_fees": [dict(r) for r in manual]}
    finally:
        conn.close()


@router.post("/challan/{chid}/manual")
def add_manual_charge(chid: str, body: ManualChargeCreate,
                       session: dict = Depends(require_role("super_admin"))):
    if body.amount <= 0:
        return json_err("Amount must be greater than zero", 400)

    charge_type = body.charge_type.strip()
    if charge_type.lower() not in KNOWN_CHARGE_TYPES:
        charge_type = charge_type or "Custom"

    conn = get_conn()
    try:
        ch = conn.execute(
            "SELECT fc.*, s.name student_name FROM fee_challans fc "
            "JOIN students s ON fc.student_id=s.id WHERE fc.id=?", (chid,)).fetchone()
        if not ch:
            return json_err("Challan not found", 404)

        mfid = new_id("mf")
        conn.execute(
            "INSERT INTO manual_fees (id, challan_id, charge_type, description, amount) VALUES (?,?,?,?,?)",
            (mfid, chid, charge_type, body.description, body.amount))

        new_total = ch["total"] + body.amount
        # The amount already paid doesn't change just because a new charge
        # was added — but the total owed did, so the status must be
        # recalculated honestly rather than silently staying "Paid".
        new_status = _derive_status(new_total, ch["amount_paid"])

        conn.execute("UPDATE fee_challans SET total=?, status=? WHERE id=?", (new_total, new_status, chid))

        audit(session, "Fees", "Manual Charge",
              f"Added {charge_type} of Rs.{body.amount} to {ch['student_name']}'s challan "
              f"(status recalculated to {new_status})", conn=conn)
        conn.commit()

        response = {"id": mfid, "new_total": new_total, "new_status": new_status}
        if ch["status"] == "Paid" and new_status != "Paid":
            response["note"] = (
                f"This challan was fully paid before. Since a new charge was added, its status "
                f"has been updated to '{new_status}' to reflect the additional amount owed."
            )
        return response
    finally:
        conn.close()


@router.post("/challan/{chid}/pay")
def update_payment(chid: str, body: PayRequest, session: dict = Depends(require_role("super_admin"))):
    if body.status not in PAYMENT_STATUSES:
        return json_err("Invalid payment status", 400)

    conn = get_conn()
    try:
        ch = conn.execute(
            "SELECT fc.*, s.name student_name FROM fee_challans fc "
            "JOIN students s ON fc.student_id=s.id WHERE fc.id=?", (chid,)).fetchone()
        if not ch:
            return json_err("Challan not found", 404)

        # Determine the actual amount_paid based on the requested status,
        # so "status" and "amount_paid" can never disagree with each other.
        if body.status == "Paid":
            amount_paid = ch["total"]
        elif body.status == "Unpaid":
            amount_paid = 0
        else:  # "Partially Paid"
            if body.amount_paid is None:
                return json_err("amount_paid is required when setting status to 'Partially Paid'", 400)
            if body.amount_paid <= 0 or body.amount_paid >= ch["total"]:
                return json_err(
                    f"For 'Partially Paid', amount_paid must be between 0 and {ch['total']} (exclusive)", 400
                )
            amount_paid = body.amount_paid

        if ch["status"] == body.status and ch["amount_paid"] == amount_paid:
            return json_err(f"This challan is already marked '{body.status}' with this amount", 400)

        paid_at = now_iso() if body.status == "Paid" else ch["paid_at"]
        conn.execute("UPDATE fee_challans SET status=?, amount_paid=?, paid_at=? WHERE id=?",
                     (body.status, amount_paid, paid_at, chid))
        audit(session, "Fees", "Payment",
              f"Set {ch['student_name']}'s challan to {body.status} (Rs.{amount_paid} of Rs.{ch['total']})",
              conn=conn)
        conn.commit()
        return {"message": "Payment status updated"}
    finally:
        conn.close()


@router.get("/report")
def fee_report(status: str = None, month: int = None, year: int = None,
               session: dict = Depends(require_role("super_admin", "principal"))):
    conn = get_conn()
    try:
        sql = ("SELECT fc.*, s.name student_name, s.roll_number, c.name class_name FROM fee_challans fc "
               "JOIN students s ON fc.student_id=s.id LEFT JOIN classes c ON s.class_id=c.id WHERE 1=1")
        params = []
        if status: sql += " AND fc.status=?"; params.append(status)
        if month: sql += " AND fc.month=?"; params.append(month)
        if year: sql += " AND fc.year=?"; params.append(year)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY fc.year, fc.month", params).fetchall()]

        total_amt = sum(r["total"] for r in rows)
        collected = sum(r["amount_paid"] for r in rows)  # now a real sum of actual amounts paid
        return {"report": rows, "summary": {
            "count": len(rows), "total": total_amt,
            "collected": collected,
            "outstanding": total_amt - collected,
        }}
    finally:
        conn.close()