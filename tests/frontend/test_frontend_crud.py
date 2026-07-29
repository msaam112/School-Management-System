"""Frontend CRUD tests that cross-check the UI against the real API —
catching the class of bug where the UI 'looks' successful but the
database was never actually updated."""
import json
import urllib.request
from playwright.sync_api import Page, expect


def login_as_admin(page: Page, base_url: str, school_setup: dict):
    page.goto(base_url)
    page.wait_for_selector("#boot-loader", state="hidden", timeout=5000)
    page.click("text=Staff Login")
    page.fill('input[name="email"]', school_setup["admin_email"])
    page.fill('input[name="password"]', school_setup["admin_password"])
    page.click('button:has-text("Sign In")')
    expect(page.locator("#main-screen")).to_be_visible(timeout=5000)


def api_get(base_url, path):
    """Direct, UI-independent check against the real backend — the source of truth."""
    with urllib.request.urlopen(base_url + path) as r:
        return json.loads(r.read())


def test_add_student_actually_persists_to_database(page: Page, base_url, school_setup):
    """The UI must show the new student AND the database must actually
    contain it — checked independently via a raw API call, not the UI."""
    login_as_admin(page, base_url, school_setup)

    page.click("text=Students")
    expect(page.locator("h2:has-text('Students')")).to_be_visible()

    page.click("button:has-text('Add Student')")
    page.fill('input[name="name"]', "Playwright Kid")
    page.fill('input[name="roll_number"]', "PW-001")
    page.fill('input[name="parent_name"]', "Playwright Parent")
    page.fill('input[name="parent_cnic"]', "99900-1111111-1")
    page.click('.modal button:has-text("Save")')

    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)
    expect(page.locator("table")).to_contain_text("Playwright Kid")

    # Cross-check: hit the real API directly (bypassing the UI entirely)
    # to confirm the record genuinely exists server-side.
    cookie = page.context.cookies()[0]
    req = urllib.request.Request(base_url + "/api/students/search?q=PW-001")
    req.add_header("Cookie", f"{cookie['name']}={cookie['value']}")
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    assert any(s["roll_number"] == "PW-001" for s in data["students"]), \
        "UI showed success but student was NOT found via direct API check"


def test_edit_student_status_persists_after_reload(page: Page, base_url, school_setup):
    """Edits must survive a full page reload — proves the change was
    saved server-side, not just held in in-memory JS state."""
    login_as_admin(page, base_url, school_setup)
    page.click("text=Students")

    page.click("button:has-text('Add Student')")
    page.fill('input[name="name"]', "Reload Test Kid")
    page.fill('input[name="roll_number"]', "PW-RELOAD")
    page.fill('input[name="parent_name"]', "Reload Parent")
    page.fill('input[name="parent_cnic"]', "99900-2222222-2")
    page.click('.modal button:has-text("Save")')
    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)

    row = page.locator("tr", has_text="Reload Test Kid")
    row.locator('button:has-text("Edit")').click()
    page.select_option('select[name="status"]', "inactive")
    page.click('.modal button:has-text("Save")')
    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)

    # Full reload — if the earlier change only lived in JS memory, it'd be gone now.
    page.reload()
    page.wait_for_selector("#boot-loader", state="hidden", timeout=5000)
    page.click("text=Students")

    row_after_reload = page.locator("tr", has_text="Reload Test Kid")
    expect(row_after_reload).to_contain_text("inactive")


def test_delete_student_actually_removes_from_database(page: Page, base_url, school_setup):
    login_as_admin(page, base_url, school_setup)
    page.click("text=Students")

    page.click("button:has-text('Add Student')")
    page.fill('input[name="name"]', "Delete Test Kid")
    page.fill('input[name="roll_number"]', "PW-DELETE")
    page.fill('input[name="parent_name"]', "Delete Parent")
    page.fill('input[name="parent_cnic"]', "99900-3333333-3")
    page.click('.modal button:has-text("Save")')
    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)

    row = page.locator("tr", has_text="Delete Test Kid")
    row.locator('button:has-text("Delete")').click()
    page.click('.modal button:has-text("Yes, proceed")')
    expect(page.locator(".toast")).to_be_visible(timeout=5000)

    expect(page.locator("table")).not_to_contain_text("Delete Test Kid", timeout=5000)

    # Cross-check against the real API.
    cookie = page.context.cookies()[0]
    req = urllib.request.Request(base_url + "/api/students/search?q=PW-DELETE")
    req.add_header("Cookie", f"{cookie['name']}={cookie['value']}")
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    assert len(data["students"]) == 0, "UI removed the row but student still exists in the database"


def test_add_teacher_shows_generated_password_and_can_login(page: Page, base_url, school_setup):
    """Cross-checks the trickiest kind of bug: a value only ever shown
    once (the generated password) must be the ACTUAL working password."""
    login_as_admin(page, base_url, school_setup)
    page.click("text=Teachers")

    page.click("button:has-text('Add Teacher')")
    page.fill('input[name="name"]', "Playwright Teacher")
    page.fill('.modal input[name="email"]', "pwteacher@test.edu")
    page.click('.modal button:has-text("Save")')

    expect(page.locator("text=Teacher account created")).to_be_visible(timeout=5000)
    password_field = page.locator('.modal input[readonly]').nth(1)
    generated_password = password_field.input_value()
    assert len(generated_password) > 0

    page.click('.modal button:has-text("Done")')

    # Now prove that exact password genuinely works, via a real login call.
    payload = json.dumps({
        "type": "staff", "email": "pwteacher@test.edu", "password": generated_password,
    }).encode()
    req = urllib.request.Request(base_url + "/api/auth/login", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    assert result["role"] == "teacher"