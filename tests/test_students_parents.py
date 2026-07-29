"""Tests for FR-4 (Students), FR-5 (Parents), and BR-5 (parent data isolation)
— mirrors Module 4 verification."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import login_as, login_as_parent


@pytest.fixture()
def admin(client, setup_school):
    login_as(client, setup_school["admin_email"], setup_school["admin_password"])
    return client


def test_create_student_auto_creates_parent(admin, setup_school):
    r = admin.post("/api/students", json={
        "name": "Student One", "roll_number": "SP-001",
        "class_id": setup_school["grade5_id"], "section_id": setup_school["grade5_sec_a"],
        "parent_name": "Parent One", "parent_cnic": "11111-1111111-1",
    })
    assert r.status_code == 200, r.text
    assert "id" in r.json()

    parents = admin.get("/api/parents").json()["parents"]
    assert any(p["cnic"] == "11111-1111111-1" for p in parents)


def test_duplicate_roll_number_rejected(admin, setup_school):
    admin.post("/api/students", json={
        "name": "Dup A", "roll_number": "SP-DUP", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "P", "parent_cnic": "22222-2222222-2",
    })
    r = admin.post("/api/students", json={
        "name": "Dup B", "roll_number": "SP-DUP", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "P2", "parent_cnic": "33333-3333333-3",
    })
    assert r.status_code == 400
    assert "already in use" in r.json()["error"].lower()


def test_student_update_and_delete(admin, setup_school):
    r = admin.post("/api/students", json={
        "name": "To Edit", "roll_number": "SP-EDIT", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "P", "parent_cnic": "44444-4444444-4",
    })
    sid = r.json()["id"]

    r2 = admin.put(f"/api/students/{sid}", json={"status": "inactive"})
    assert r2.status_code == 200

    detail = admin.get(f"/api/students/{sid}").json()["student"]
    assert detail["status"] == "inactive"

    r3 = admin.delete(f"/api/students/{sid}")
    assert r3.status_code == 200

    assert admin.get(f"/api/students/{sid}").status_code == 404


def test_parent_delete_blocked_when_linked_to_student(admin, setup_school):
    r = admin.post("/api/students", json={
        "name": "Linked Kid", "roll_number": "SP-LINK", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "Linked Parent", "parent_cnic": "55555-5555555-5",
    })
    assert r.status_code == 200
    parents = admin.get("/api/parents").json()["parents"]
    pid = next(p["id"] for p in parents if p["cnic"] == "55555-5555555-5")

    r2 = admin.delete(f"/api/parents/{pid}")
    assert r2.status_code == 400
    assert "linked to students" in r2.json()["error"].lower()


def test_parent_can_only_see_own_child_not_classmates(setup_school):
    """The critical BR-5 test: two students in the SAME class/section, parent
    of one must not see the other, even though an admin sees both."""
    admin_client = TestClient(app)
    login_as(admin_client, setup_school["admin_email"], setup_school["admin_password"])

    r1 = admin_client.post("/api/students", json={
        "name": "Sibling A", "roll_number": "ISO-001", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "Parent Iso A", "parent_cnic": "66666-6666666-6",
    })
    r2 = admin_client.post("/api/students", json={
        "name": "Sibling B", "roll_number": "ISO-002", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "Parent Iso B", "parent_cnic": "77777-7777777-7",
    })
    assert r1.status_code == 200 and r2.status_code == 200

    # Admin sees both.
    admin_students = admin_client.get("/api/students").json()["students"]
    rolls = {s["roll_number"] for s in admin_students}
    assert "ISO-001" in rolls and "ISO-002" in rolls

    # Parent A, logging in fresh, must see ONLY their own child.
    parent_client = TestClient(app)
    login_as_parent(parent_client, "66666-6666666-6", "ISO-001")
    parent_view = parent_client.get("/api/students").json()["students"]
    assert len(parent_view) == 1
    assert parent_view[0]["roll_number"] == "ISO-001"

    # And they cannot fetch the other student directly by ID either.
    other_id = next(s["id"] for s in admin_students if s["roll_number"] == "ISO-002")
    r3 = parent_client.get(f"/api/students/{other_id}")
    assert r3.status_code == 403


def test_student_search(admin, setup_school):
    admin.post("/api/students", json={
        "name": "Searchable Kid", "roll_number": "SEARCH-01", "class_id": setup_school["grade5_id"],
        "section_id": setup_school["grade5_sec_a"], "parent_name": "P", "parent_cnic": "88888-8888888-8",
    })
    r = admin.get("/api/students/search?q=Searchable")
    assert r.status_code == 200
    assert any(s["roll_number"] == "SEARCH-01" for s in r.json()["students"])