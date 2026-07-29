"""Shared pytest fixtures: an isolated test database + a real TestClient
hitting the actual FastAPI app, so tests exercise real HTTP behavior."""
import os
import tempfile
import pytest

# IMPORTANT: point at a temp DB BEFORE importing anything from app.*,
# since app.config reads SMS_DB at import time.
TEST_DB = tempfile.mktemp(suffix=".db", prefix="sms_test_")
os.environ["SMS_DB"] = TEST_DB

from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Runs once per test session: build the schema in the temp DB."""
    init_db()
    yield
    try:
        os.remove(TEST_DB)
    except Exception:
        pass


@pytest.fixture()
def client():
    """A fresh TestClient per test. Cookies are isolated per-client instance,
    so each test gets its own independent 'browser session'."""
    return TestClient(app)


@pytest.fixture(scope="session")
def setup_school(_init_test_db):
    """Run the one-time school setup once for the whole test session, and
    return the admin credentials + created class/section IDs for reuse."""
    c = TestClient(app)
    resp = c.post("/api/setup", json={
        "school_name": "Test Grammar School",
        "admin_email": "sa@test.edu",
        "admin_password": "admin123",
        "classes": [
            {"name": "Grade 5", "sections": ["A", "B"]},
            {"name": "Grade 6", "sections": ["A"]},
        ],
    })
    assert resp.status_code == 200, resp.text

    classes = c.get("/api/classes").json()["classes"]
    sections = c.get("/api/sections").json()["sections"]

    return {
        "admin_email": "sa@test.edu",
        "admin_password": "admin123",
        "grade5_id": next(c["id"] for c in classes if c["name"] == "Grade 5"),
        "grade6_id": next(c["id"] for c in classes if c["name"] == "Grade 6"),
        "grade5_sec_a": next(s["id"] for s in sections if s["name"] == "A" and s["class_id"] == next(c["id"] for c in classes if c["name"] == "Grade 5")),
    }


def login_as(client, email, password):
    """Helper: log a TestClient in as staff, asserting success."""
    r = client.post("/api/auth/login", json={"type": "staff", "email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def login_as_parent(client, cnic, roll):
    r = client.post("/api/auth/login", json={"type": "parent", "cnic": cnic, "roll": roll})
    assert r.status_code == 200, r.text
    return r.json()