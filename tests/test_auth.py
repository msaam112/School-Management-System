"""Tests for FR-1 (Auth) and FR-2 (Setup Wizard) — mirrors Module 2 verification."""
from tests.conftest import login_as, login_as_parent


def test_setup_status_reflects_completion(client, setup_school):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["setup_done"] is True


def test_setup_cannot_run_twice(client, setup_school):
    """BR-1: the setup wizard shall execute only once."""
    r = client.post("/api/setup", json={
        "school_name": "Another School",
        "admin_email": "x@x.com",
        "admin_password": "whatever1",
        "classes": [{"name": "X", "sections": []}],
    })
    assert r.status_code == 400
    assert "already configured" in r.json()["error"].lower()


def test_staff_login_success(client, setup_school):
    data = login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    assert data["role"] == "super_admin"


def test_staff_login_wrong_password(client, setup_school):
    r = client.post("/api/auth/login", json={
        "type": "staff", "email": setup_school["admin_email"], "password": "wrongpass"
    })
    assert r.status_code == 401


def test_staff_login_unknown_email(client, setup_school):
    r = client.post("/api/auth/login", json={
        "type": "staff", "email": "nobody@nowhere.com", "password": "whatever1"
    })
    assert r.status_code == 401


def test_me_requires_authentication(client, setup_school):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_returns_correct_role_after_login(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "super_admin"


def test_logout_clears_session(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    assert client.get("/api/auth/me").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 200

    assert client.get("/api/auth/me").status_code == 401


def test_parent_login_requires_matching_cnic_and_roll(client, setup_school):
    """Register a student+parent first via the admin session, then test parent login."""
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    r = client.post("/api/students", json={
        "name": "Auth Test Student", "roll_number": "AUTH-001",
        "class_id": setup_school["grade5_id"], "section_id": setup_school["grade5_sec_a"],
        "parent_name": "Auth Test Parent", "parent_cnic": "99999-0000000-0",
    })
    assert r.status_code == 200, r.text

    # Correct CNIC + roll -> success
    r = client.post("/api/auth/login", json={"type": "parent", "cnic": "99999-0000000-0", "roll": "AUTH-001"})
    assert r.status_code == 200
    assert r.json()["role"] == "parent"

    # Wrong CNIC for a real roll -> rejected
    r2 = client.post("/api/auth/login", json={"type": "parent", "cnic": "00000-0000000-0", "roll": "AUTH-001"})
    assert r2.status_code == 401

    # Unknown roll entirely -> rejected
    r3 = client.post("/api/auth/login", json={"type": "parent", "cnic": "99999-0000000-0", "roll": "NOPE-999"})
    assert r3.status_code == 401