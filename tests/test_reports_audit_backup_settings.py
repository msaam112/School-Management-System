"""Tests for FR-15 (Reports), FR-16 (Audit Log), FR-17 (Backup), FR-18 (Settings)
— mirrors Modules 11, 12, 13, 14 verification."""
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


# ------------------------------------------------------------------ Reports (spot-check a representative sample)
def test_student_list_report_returns_pdf(admin):
    r = admin.get("/api/reports/students/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")


def test_teacher_list_report_returns_pdf(admin):
    r = admin.get("/api/reports/teachers/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_dashboard_stats_report_super_admin_only(admin, client, setup_school):
    r = admin.get("/api/reports/dashboard-stats/pdf")
    assert r.status_code == 200

    # A teacher account should NOT be able to access this Super-Admin-only report.
    n = next(_counter)
    t = admin.post("/api/teachers", json={"name": f"Report Teacher {n}", "email": f"reportt{n}@test.edu"})
    password = t.json()["password"]
    t_client = TestClient(app)
    login_as(t_client, f"reportt{n}@test.edu", password)
    r2 = t_client.get("/api/reports/dashboard-stats/pdf")
    assert r2.status_code == 403


def test_fee_challan_pdf_accessible_by_parent(admin, setup_school):
    n = next(_counter)
    cls_id = setup_school["grade5_id"]
    sec_id = setup_school["grade5_sec_a"]
    s = admin.post("/api/students", json={
        "name": f"PDF Student {n}", "roll_number": f"PDF-{n:04d}",
        "class_id": cls_id, "section_id": sec_id,
        "parent_name": "PDF Parent", "parent_cnic": f"40404-0404{n:03d}-0",
    })
    sid = s.json()["id"]
    existing_structures = admin.get("/api/fee-structures").json()["structures"]
    if not any(fs["class_id"] == cls_id for fs in existing_structures):
        admin.post("/api/fee-structures", json={"class_id": cls_id, "tuition_fee": 1000})
    admin.post("/api/fees/generate", json={"month": 11, "year": 2099, "class_id": cls_id})
    challans = admin.get(f"/api/fees/challans?year=2099&month=11").json()["challans"]
    entry = next(c for c in challans if c["student_id"] == sid)

    from tests.conftest import login_as_parent
    parent_client = TestClient(app)
    login_as_parent(parent_client, f"40404-0404{n:03d}-0", f"PDF-{n:04d}")

    r = parent_client.get(f"/api/reports/fees/challan/{entry['id']}/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


# ------------------------------------------------------------------ Audit Log
def test_audit_log_super_admin_only(admin, setup_school):
    r = admin.get("/api/audit")
    assert r.status_code == 200
    assert len(r.json()["logs"]) > 0  # setup itself creates an entry

    n = next(_counter)
    t = admin.post("/api/teachers", json={"name": f"Audit Teacher {n}", "email": f"audit{n}@test.edu"})
    password = t.json()["password"]
    t_client = TestClient(app)
    login_as(t_client, f"audit{n}@test.edu", password)
    r2 = t_client.get("/api/audit")
    assert r2.status_code == 403


def test_audit_log_records_student_creation(admin, setup_school):
    n = next(_counter)
    admin.post("/api/students", json={
        "name": f"Audit Trail Student {n}", "roll_number": f"AUD-{n:04d}",
        "class_id": setup_school["grade5_id"], "section_id": setup_school["grade5_sec_a"],
        "parent_name": "P", "parent_cnic": f"50505-0505{n:03d}-0",
    })
    logs = admin.get("/api/audit").json()["logs"]
    assert any(f"Audit Trail Student {n}" in (log.get("description") or "") for log in logs)


# ------------------------------------------------------------------ Backup
def test_backup_super_admin_only(admin, setup_school):
    r = admin.post("/api/backup")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    body = r.json()
    assert "students" in body
    assert "users" in body
    assert "audit_log" in body

    n = next(_counter)
    t = admin.post("/api/teachers", json={"name": f"Backup Teacher {n}", "email": f"backup{n}@test.edu"})
    password = t.json()["password"]
    t_client = TestClient(app)
    login_as(t_client, f"backup{n}@test.edu", password)
    r2 = t_client.post("/api/backup")
    assert r2.status_code == 403


# ------------------------------------------------------------------ Settings & User Privileges
def test_update_school_settings(admin):
    r = admin.put("/api/settings", json={"motto": "Test Motto Updated", "settings": {"pass_mark": "40"}})
    assert r.status_code == 200

    d = admin.get("/api/settings").json()
    assert d["school"]["motto"] == "Test Motto Updated"
    assert d["settings"]["pass_mark"] == "40"


def test_list_users_excludes_system_account(admin):
    r = admin.get("/api/settings/users")
    assert r.status_code == 200
    users = r.json()["users"]
    assert not any(u["role"] == "system" for u in users)


def test_disable_and_reenable_user_blocks_login(admin, setup_school):
    n = next(_counter)
    t = admin.post("/api/teachers", json={"name": f"Disable Teacher {n}", "email": f"disable{n}@test.edu"})
    tid = t.json()["id"]
    password = t.json()["password"]

    # Confirm login works while active.
    fresh = TestClient(app)
    r1 = fresh.post("/api/auth/login", json={"type": "staff", "email": f"disable{n}@test.edu", "password": password})
    assert r1.status_code == 200

    users = admin.get("/api/settings/users").json()["users"]
    uid = next(u["id"] for u in users if u["email"] == f"disable{n}@test.edu")

    r2 = admin.put(f"/api/settings/users/{uid}/status", json={"status": "disabled"})
    assert r2.status_code == 200

    fresh2 = TestClient(app)
    r3 = fresh2.post("/api/auth/login", json={"type": "staff", "email": f"disable{n}@test.edu", "password": password})
    assert r3.status_code == 403

    # Re-enable and confirm login works again.
    admin.put(f"/api/settings/users/{uid}/status", json={"status": "active"})
    fresh3 = TestClient(app)
    r4 = fresh3.post("/api/auth/login", json={"type": "staff", "email": f"disable{n}@test.edu", "password": password})
    assert r4.status_code == 200


def test_reset_password_generates_working_credentials(admin, setup_school):
    n = next(_counter)
    t = admin.post("/api/teachers", json={"name": f"Reset Teacher {n}", "email": f"reset{n}@test.edu"})
    users = admin.get("/api/settings/users").json()["users"]
    uid = next(u["id"] for u in users if u["email"] == f"reset{n}@test.edu")

    r = admin.post(f"/api/settings/users/{uid}/reset-password")
    assert r.status_code == 200
    new_password = r.json()["password"]

    fresh = TestClient(app)
    r2 = fresh.post("/api/auth/login", json={"type": "staff", "email": f"reset{n}@test.edu", "password": new_password})
    assert r2.status_code == 200


def test_cannot_disable_super_admin(admin, setup_school):
    users = admin.get("/api/settings/users").json()["users"]
    sa_uid = next(u["id"] for u in users if u["role"] == "super_admin")
    r = admin.put(f"/api/settings/users/{sa_uid}/status", json={"status": "disabled"})
    assert r.status_code == 400