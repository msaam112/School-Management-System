"""Tests for FR-11/FR-12 (Exams & Results), FR-13 (Promotion), FR-14 (Fees)
— mirrors Modules 8, 9, 10 verification."""
import itertools
import pytest
from tests.conftest import login_as

_counter = itertools.count()


@pytest.fixture()
def admin(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    return client


def make_student(admin, setup_school, class_id=None, section_id=None):
    n = next(_counter)
    class_id = class_id or setup_school["grade5_id"]
    section_id = section_id or setup_school["grade5_sec_a"]
    r = admin.post("/api/students", json={
        "name": f"Exam Student {n}", "roll_number": f"EXM-{n:04d}",
        "class_id": class_id, "section_id": section_id,
        "parent_name": "P", "parent_cnic": f"30303-0303{n:03d}-0",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_subject_and_assignment(admin, setup_school, class_id=None):
    n = next(_counter)
    class_id = class_id or setup_school["grade5_id"]
    sub = admin.post("/api/subjects", json={"name": f"Exam Subject {n}"})
    sub_id = sub.json()["id"]
    t = admin.post("/api/teachers", json={"name": f"Exam Teacher {n}", "email": f"examt{n}@test.edu"})
    tid = t.json()["id"]
    a = admin.post("/api/assignments", json={"teacher_id": tid, "class_id": class_id, "subject_id": sub_id})
    assert a.status_code == 200
    return sub_id


# ------------------------------------------------------------------ Exams & Results
def test_grade_and_pass_fail_calculated_correctly(admin, setup_school):
    sid = make_student(admin, setup_school)
    sub_id = make_subject_and_assignment(admin, setup_school)

    e = admin.post("/api/exams", json={"name": "Grade Test Exam", "class_id": setup_school["grade5_id"]})
    eid = e.json()["id"]

    r = admin.post(f"/api/exams/{eid}/marks", json={
        "subject_id": sub_id, "marks": [{"student_id": sid, "obtained": 92, "total": 100}],
    })
    assert r.status_code == 200

    results = admin.get(f"/api/exams/{eid}/results").json()["results"]
    entry = next(x for x in results if x["student_id"] == sid)
    assert entry["grade"] == "A+"
    assert entry["pass_fail"] == "Pass"
    assert entry["percentage"] == 92.0


def test_failing_grade_calculated_correctly(admin, setup_school):
    sid = make_student(admin, setup_school)
    sub_id = make_subject_and_assignment(admin, setup_school)

    e = admin.post("/api/exams", json={"name": "Fail Test Exam", "class_id": setup_school["grade5_id"]})
    eid = e.json()["id"]

    admin.post(f"/api/exams/{eid}/marks", json={
        "subject_id": sub_id, "marks": [{"student_id": sid, "obtained": 20, "total": 100}],
    })

    results = admin.get(f"/api/exams/{eid}/results").json()["results"]
    entry = next(x for x in results if x["student_id"] == sid)
    assert entry["grade"] == "F"
    assert entry["pass_fail"] == "Fail"


def test_exam_delete_removes_results(admin, setup_school):
    sid = make_student(admin, setup_school)
    sub_id = make_subject_and_assignment(admin, setup_school)
    e = admin.post("/api/exams", json={"name": "Delete Test Exam", "class_id": setup_school["grade5_id"]})
    eid = e.json()["id"]
    admin.post(f"/api/exams/{eid}/marks", json={
        "subject_id": sub_id, "marks": [{"student_id": sid, "obtained": 70, "total": 100}],
    })

    r = admin.delete(f"/api/exams/{eid}")
    assert r.status_code == 200
    assert admin.get(f"/api/exams/{eid}").status_code == 404


# ------------------------------------------------------------------ Promotion
def test_passing_student_promotes_failing_student_retained(admin, setup_school):
    pass_sid = make_student(admin, setup_school)
    fail_sid = make_student(admin, setup_school)
    sub_id = make_subject_and_assignment(admin, setup_school)

    e = admin.post("/api/exams", json={"name": "Promotion Test Exam", "class_id": setup_school["grade5_id"]})
    eid = e.json()["id"]
    admin.post(f"/api/exams/{eid}/marks", json={
        "subject_id": sub_id,
        "marks": [
            {"student_id": pass_sid, "obtained": 80, "total": 100},
            {"student_id": fail_sid, "obtained": 10, "total": 100},
        ],
    })

    r = admin.post("/api/promote", json={
        "academic_year": "2099",
        "promotions": [
            {"student_id": pass_sid, "to_class_id": setup_school["grade6_id"]},
            {"student_id": fail_sid, "to_class_id": setup_school["grade6_id"]},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["promoted"] == 1
    assert body["retained"] == 1

    # Verify the failing student's class_id genuinely did NOT change.
    fail_detail = admin.get(f"/api/students/{fail_sid}").json()["student"]
    assert fail_detail["class_id"] == setup_school["grade5_id"]

    pass_detail = admin.get(f"/api/students/{pass_sid}").json()["student"]
    assert pass_detail["class_id"] == setup_school["grade6_id"]


def test_promotion_override_forces_promotion_despite_failure(admin, setup_school):
    fail_sid = make_student(admin, setup_school)
    sub_id = make_subject_and_assignment(admin, setup_school)

    e = admin.post("/api/exams", json={"name": "Override Test Exam", "class_id": setup_school["grade5_id"]})
    eid = e.json()["id"]
    admin.post(f"/api/exams/{eid}/marks", json={
        "subject_id": sub_id, "marks": [{"student_id": fail_sid, "obtained": 5, "total": 100}],
    })

    r = admin.post("/api/promote", json={
        "academic_year": "2099",
        "promotions": [{"student_id": fail_sid, "to_class_id": setup_school["grade6_id"], "override": True}],
    })
    assert r.status_code == 200
    assert r.json()["promoted"] == 1

    detail = admin.get(f"/api/students/{fail_sid}").json()["student"]
    assert detail["class_id"] == setup_school["grade6_id"]


# ------------------------------------------------------------------ Fees
def test_fee_challan_generation_and_totals(admin, setup_school):
    n = next(_counter)
    cls = admin.post("/api/classes", json={"name": f"Fee Test Class {n}"})
    cid = cls.json()["id"]
    sec = admin.post("/api/sections", json={"class_id": cid, "name": "A"})
    sec_id = sec.json()["id"]
    sid = make_student(admin, setup_school, class_id=cid, section_id=sec_id)

    admin.post("/api/fee-structures", json={
        "class_id": cid, "admission_fee": 1000, "tuition_fee": 2000, "exam_fee": 300,
    })

    r = admin.post("/api/fees/generate", json={"month": 6, "year": 2099, "class_id": cid})
    assert r.status_code == 200
    assert r.json()["count"] == 1

    challans = admin.get("/api/fees/challans?year=2099&month=6").json()["challans"]
    entry = next(c for c in challans if c["student_id"] == sid)
    assert entry["total"] == 3300  # 1000 + 2000 + 300, first challan includes admission fee
    assert entry["status"] == "Unpaid"


def test_duplicate_challan_not_regenerated(admin, setup_school):
    n = next(_counter)
    cls = admin.post("/api/classes", json={"name": f"Fee Dup Class {n}"})
    cid = cls.json()["id"]
    sec = admin.post("/api/sections", json={"class_id": cid, "name": "A"})
    sec_id = sec.json()["id"]
    make_student(admin, setup_school, class_id=cid, section_id=sec_id)
    admin.post("/api/fee-structures", json={"class_id": cid, "tuition_fee": 1500})

    r1 = admin.post("/api/fees/generate", json={"month": 7, "year": 2099, "class_id": cid})
    assert r1.json()["count"] == 1

    r2 = admin.post("/api/fees/generate", json={"month": 7, "year": 2099, "class_id": cid})
    assert r2.json()["count"] == 0


def test_manual_charge_updates_total(admin, setup_school):
    n = next(_counter)
    cls = admin.post("/api/classes", json={"name": f"Manual Charge Class {n}"})
    cid = cls.json()["id"]
    sec = admin.post("/api/sections", json={"class_id": cid, "name": "A"})
    sec_id = sec.json()["id"]
    make_student(admin, setup_school, class_id=cid, section_id=sec_id)
    admin.post("/api/fee-structures", json={"class_id": cid, "tuition_fee": 1000})
    admin.post("/api/fees/generate", json={"month": 8, "year": 2099, "class_id": cid})

    challans = admin.get("/api/fees/challans?year=2099&month=8").json()["challans"]
    chid = challans[0]["id"]
    original_total = challans[0]["total"]

    r = admin.post(f"/api/fees/challan/{chid}/manual", json={"charge_type": "Fine", "amount": 150})
    assert r.status_code == 200

    updated = admin.get(f"/api/fees/challan/{chid}").json()["challan"]
    assert updated["total"] == original_total + 150


def test_payment_status_update(admin, setup_school):
    n = next(_counter)
    cls = admin.post("/api/classes", json={"name": f"Pay Test Class {n}"})
    cid = cls.json()["id"]
    sec = admin.post("/api/sections", json={"class_id": cid, "name": "A"})
    sec_id = sec.json()["id"]
    make_student(admin, setup_school, class_id=cid, section_id=sec_id)
    admin.post("/api/fee-structures", json={"class_id": cid, "tuition_fee": 500})
    admin.post("/api/fees/generate", json={"month": 9, "year": 2099, "class_id": cid})

    challans = admin.get("/api/fees/challans?year=2099&month=9").json()["challans"]
    chid = challans[0]["id"]

    r = admin.post(f"/api/fees/challan/{chid}/pay", json={"status": "Paid"})
    assert r.status_code == 200

    updated = admin.get(f"/api/fees/challan/{chid}").json()["challan"]
    assert updated["status"] == "Paid"


def test_invalid_payment_status_rejected(admin, setup_school):
    n = next(_counter)
    cls = admin.post("/api/classes", json={"name": f"Invalid Pay Class {n}"})
    cid = cls.json()["id"]
    sec = admin.post("/api/sections", json={"class_id": cid, "name": "A"})
    sec_id = sec.json()["id"]
    make_student(admin, setup_school, class_id=cid, section_id=sec_id)
    admin.post("/api/fee-structures", json={"class_id": cid, "tuition_fee": 500})
    admin.post("/api/fees/generate", json={"month": 10, "year": 2099, "class_id": cid})

    challans = admin.get("/api/fees/challans?year=2099&month=10").json()["challans"]
    chid = challans[0]["id"]

    r = admin.post(f"/api/fees/challan/{chid}/pay", json={"status": "paid"})  # wrong casing
    assert r.status_code == 400