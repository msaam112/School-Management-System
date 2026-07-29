"""Tests for FR-6 (Teachers), FR-7 (Classes/Sections), FR-8 (Subjects/Assignments)
— mirrors Modules 5 and 6 verification."""
import pytest
from tests.conftest import login_as


@pytest.fixture()
def admin(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    return client


# ------------------------------------------------------------------ Teachers
def test_create_teacher_creates_login_account(admin):
    r = admin.post("/api/teachers", json={
        "name": "Teacher One", "email": "teacher1@test.edu", "qualification": "M.Sc",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body and "password" in body


def test_new_teacher_can_log_in_with_generated_password(client, setup_school):
    admin = client
    login_as(admin, setup_school["admin_email"], setup_school["admin_password"])
    r = admin.post("/api/teachers", json={
        "name": "Login Test Teacher", "email": "logintest@test.edu", "qualification": "B.Ed",
    })
    password = r.json()["password"]

    from fastapi.testclient import TestClient
    from app.main import app
    fresh = TestClient(app)
    r2 = fresh.post("/api/auth/login", json={"type": "staff", "email": "logintest@test.edu", "password": password})
    assert r2.status_code == 200
    assert r2.json()["role"] == "teacher"


def test_class_incharge_gets_class_incharge_role(admin, setup_school):
    r = admin.post("/api/teachers", json={
        "name": "Incharge Teacher", "email": "incharge1@test.edu", "qualification": "B.Ed",
        "is_class_incharge": True, "class_id": setup_school["grade5_id"],
    })
    tid = r.json()["id"]
    teachers = admin.get("/api/teachers").json()["teachers"]
    t = next(x for x in teachers if x["id"] == tid)
    assert t["is_class_incharge"] == 1
    assert t["class_id"] == setup_school["grade5_id"]


def test_class_id_not_persisted_when_not_incharge(admin, setup_school):
    """Regression test for the bug found during Module 15 manual testing:
    a non-incharge teacher must never end up with a stray class_id."""
    r = admin.post("/api/teachers", json={
        "name": "Regular Teacher", "email": "regular1@test.edu", "qualification": "M.A",
    })
    tid = r.json()["id"]

    # Explicitly try to sneak a class_id in via update while is_class_incharge stays false.
    r2 = admin.put(f"/api/teachers/{tid}", json={"class_id": setup_school["grade5_id"]})
    assert r2.status_code == 200

    teachers = admin.get("/api/teachers").json()["teachers"]
    t = next(x for x in teachers if x["id"] == tid)
    assert t["is_class_incharge"] == 0
    assert t["class_id"] is None, "class_id leaked onto a non-incharge teacher"


def test_delete_teacher_removes_login_account(admin):
    r = admin.post("/api/teachers", json={
        "name": "Delete Me", "email": "deleteme1@test.edu", "qualification": "M.A",
    })
    tid = r.json()["id"]
    r2 = admin.delete(f"/api/teachers/{tid}")
    assert r2.status_code == 200
    teachers = admin.get("/api/teachers").json()["teachers"]
    assert not any(t["id"] == tid for t in teachers)


# ------------------------------------------------------------------ Classes & Sections
def test_max_three_sections_per_class(admin):
    r = admin.post("/api/classes", json={"name": "Limit Test Class"})
    cid = r.json()["id"]

    for name in ["A", "B", "C"]:
        r = admin.post("/api/sections", json={"class_id": cid, "name": name})
        assert r.status_code == 200, r.text

    r4 = admin.post("/api/sections", json={"class_id": cid, "name": "D"})
    assert r4.status_code == 400
    assert "maximum" in r4.json()["error"].lower()


def test_class_delete_blocked_with_enrolled_students(admin, setup_school):
    r = admin.post("/api/students", json={
        "name": "Class Delete Test", "roll_number": "CDT-001",
        "class_id": setup_school["grade5_id"], "section_id": setup_school["grade5_sec_a"],
        "parent_name": "P", "parent_cnic": "10101-1010101-0",
    })
    assert r.status_code == 200

    r2 = admin.delete(f"/api/classes/{setup_school['grade5_id']}")
    assert r2.status_code == 400
    assert "enrolled students" in r2.json()["error"].lower()


def test_section_delete_blocked_with_enrolled_students(admin, setup_school):
    r2 = admin.delete(f"/api/sections/{setup_school['grade5_sec_a']}")
    assert r2.status_code == 400
    assert "enrolled students" in r2.json()["error"].lower()


# ------------------------------------------------------------------ Subjects & Assignments
def test_subject_delete_blocked_when_assigned(admin, setup_school):
    sub = admin.post("/api/subjects", json={"name": "Physics Test"})
    sub_id = sub.json()["id"]
    teacher = admin.post("/api/teachers", json={"name": "Physics Teacher", "email": "physics1@test.edu"})
    tid = teacher.json()["id"]

    r = admin.post("/api/assignments", json={
        "teacher_id": tid, "class_id": setup_school["grade5_id"], "subject_id": sub_id,
    })
    assert r.status_code == 200

    r2 = admin.delete(f"/api/subjects/{sub_id}")
    assert r2.status_code == 400
    assert "assigned" in r2.json()["error"].lower()


def test_duplicate_assignment_rejected(admin, setup_school):
    sub = admin.post("/api/subjects", json={"name": "Chemistry Test"})
    sub_id = sub.json()["id"]
    teacher = admin.post("/api/teachers", json={"name": "Chem Teacher", "email": "chem1@test.edu"})
    tid = teacher.json()["id"]

    body = {"teacher_id": tid, "class_id": setup_school["grade5_id"], "subject_id": sub_id}
    r1 = admin.post("/api/assignments", json=body)
    assert r1.status_code == 200

    r2 = admin.post("/api/assignments", json=body)
    assert r2.status_code == 400
    assert "already assigned" in r2.json()["error"].lower()