"""Tests for FR-9 (Student Attendance), FR-10 (Teacher Attendance), FR-9.3 (Unlock)
— mirrors Module 7 verification, including the corrected permission matrix."""
import itertools
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import login_as

_counter = itertools.count()


@pytest.fixture()
def admin(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    return client


def make_class_incharge(admin, setup_school):
    """Creates a fresh, uniquely-named class incharge + student each call,
    so tests never collide on duplicate emails/rolls."""
    n = next(_counter)
    r = admin.post("/api/teachers", json={
        "name": f"Att Test Incharge {n}", "email": f"attci{n}@test.edu", "qualification": "B.Ed",
        "is_class_incharge": True, "class_id": setup_school["grade5_id"],
    })
    assert r.status_code == 200, r.text
    password = r.json()["password"]

    s = admin.post("/api/students", json={
        "name": f"Att Test Student {n}", "roll_number": f"ATT-{n:04d}",
        "class_id": setup_school["grade5_id"], "section_id": setup_school["grade5_sec_a"],
        "parent_name": "P", "parent_cnic": f"20202-2020{n:03d}-0",
    })
    assert s.status_code == 200, s.text
    sid = s.json()["id"]

    ci_client = TestClient(app)
    login_as(ci_client, f"attci{n}@test.edu", password)
    return ci_client, sid


def test_super_admin_cannot_submit_student_attendance(admin, setup_school):
    """Regression test for the corrected permission: Super Admin is view-only."""
    r = admin.post("/api/attendance/student", json={
        "class_id": setup_school["grade5_id"],
        "records": [], "submit": True,
    })
    assert r.status_code == 403


def test_class_incharge_submit_with_correct_class_id(admin, setup_school):
    ci_client, sid = make_class_incharge(admin, setup_school)
    r = ci_client.post("/api/attendance/student", json={
        "class_id": setup_school["grade5_id"], "date": "2030-01-16",
        "records": [{"student_id": sid, "status": "Present"}], "submit": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["locked"] is True


def test_locked_attendance_rejects_resubmission(admin, setup_school):
    ci_client, sid = make_class_incharge(admin, setup_school)
    body = {
        "class_id": setup_school["grade5_id"], "date": "2030-01-17",
        "records": [{"student_id": sid, "status": "Present"}], "submit": True,
    }
    r1 = ci_client.post("/api/attendance/student", json=body)
    assert r1.status_code == 200

    r2 = ci_client.post("/api/attendance/student", json=body)
    assert r2.status_code == 400
    assert "locked" in r2.json()["error"].lower()


def test_unlock_requires_super_admin(admin, setup_school):
    ci_client, sid = make_class_incharge(admin, setup_school)
    ci_client.post("/api/attendance/student", json={
        "class_id": setup_school["grade5_id"], "date": "2030-01-18",
        "records": [{"student_id": sid, "status": "Present"}], "submit": True,
    })
    r = ci_client.post("/api/attendance/unlock", json={
        "type": "student", "date": "2030-01-18", "class_id": setup_school["grade5_id"], "reason": "test",
    })
    assert r.status_code == 403


def test_unlock_requires_reason(admin, setup_school):
    r = admin.post("/api/attendance/unlock", json={
        "type": "student", "date": "2030-01-19", "class_id": setup_school["grade5_id"], "reason": "",
    })
    assert r.status_code == 400
    assert "reason is mandatory" in r.json()["error"].lower()


def test_unlock_allows_resubmission(admin, setup_school):
    ci_client, sid = make_class_incharge(admin, setup_school)
    body = {
        "class_id": setup_school["grade5_id"], "date": "2030-01-20",
        "records": [{"student_id": sid, "status": "Present"}], "submit": True,
    }
    r1 = ci_client.post("/api/attendance/student", json=body)
    assert r1.status_code == 200

    r2 = admin.post("/api/attendance/unlock", json={
        "type": "student", "date": "2030-01-20", "class_id": setup_school["grade5_id"], "reason": "correction",
    })
    assert r2.status_code == 200

    r3 = ci_client.post("/api/attendance/student", json=body)
    assert r3.status_code == 200
    assert r3.json()["locked"] is True


# ------------------------------------------------------------------ Teacher Attendance
def test_teacher_can_view_own_attendance_only(admin, setup_school):
    n = next(_counter)
    r = admin.post("/api/teachers", json={"name": f"TAtt Teacher {n}", "email": f"tatt{n}@test.edu"})
    password = r.json()["password"]

    t_client = TestClient(app)
    login_as(t_client, f"tatt{n}@test.edu", password)

    r2 = t_client.get("/api/attendance/teacher?date=2030-02-01")
    assert r2.status_code == 200
    assert len(r2.json()["teachers"]) <= 1


def test_super_admin_can_submit_teacher_attendance_if_not_yet_submitted(admin, setup_school):
    n = next(_counter)
    r = admin.post("/api/teachers", json={"name": f"TAtt Teacher {n}", "email": f"tatt{n}@test.edu"})
    tid = r.json()["id"]

    resp = admin.post("/api/attendance/teacher", json={
        "date": "2030-02-02", "records": [{"teacher_id": tid, "status": "Present"}], "submit": True,
    })
    assert resp.status_code == 200
    assert resp.json()["locked"] is True


def test_teacher_attendance_locks_and_blocks_resubmission(admin, setup_school):
    n = next(_counter)
    r = admin.post("/api/teachers", json={"name": f"TAtt Teacher {n}", "email": f"tatt{n}@test.edu"})
    tid = r.json()["id"]
    body = {"date": "2030-02-03", "records": [{"teacher_id": tid, "status": "Present"}], "submit": True}

    r1 = admin.post("/api/attendance/teacher", json=body)
    assert r1.status_code == 200

    r2 = admin.post("/api/attendance/teacher", json=body)
    assert r2.status_code == 400
    assert "locked" in r2.json()["error"].lower()