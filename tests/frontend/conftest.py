"""Shared fixtures for frontend (Playwright) tests: spins up a real
uvicorn server against an isolated temp DB, so browser tests hit real HTTP."""
import os
import tempfile
import threading
import time
import pytest

TEST_DB = tempfile.mktemp(suffix=".db", prefix="sms_fe_test_")
os.environ["SMS_DB"] = TEST_DB
os.environ["SMS_PORT"] = "8811"

import uvicorn
from app.main import app
from app.db import init_db

BASE_URL = "http://127.0.0.1:8811"


@pytest.fixture(scope="session", autouse=True)
def _server():
    init_db()
    config = uvicorn.Config(app, host="127.0.0.1", port=8811, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen(BASE_URL + "/api/setup/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)

    yield

    server.should_exit = True
    thread.join(timeout=5)
    try:
        os.remove(TEST_DB)
    except Exception:
        pass


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def school_setup(_server, base_url):
    """Run the setup wizard once via raw HTTP (fast), so browser tests
    start from a known, populated state."""
    import urllib.request
    import json

    payload = json.dumps({
        "school_name": "Playwright Test School",
        "admin_email": "pwadmin@test.edu",
        "admin_password": "admin123",
        "classes": [{"name": "Grade 5", "sections": ["A"]}],
    }).encode()

    req = urllib.request.Request(base_url + "/api/setup", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req)

    return {"admin_email": "pwadmin@test.edu", "admin_password": "admin123"}