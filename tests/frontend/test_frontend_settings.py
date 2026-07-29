"""Frontend (Playwright) tests for Settings — specifically guards against
the sidebar-not-updating bug found during manual UI testing."""
import re
from playwright.sync_api import Page, expect


def login_as_admin(page: Page, base_url: str, school_setup: dict):
    page.goto(base_url)
    page.wait_for_selector("#boot-loader", state="hidden", timeout=5000)
    page.click("text=Staff Login")
    page.fill('input[name="email"]', school_setup["admin_email"])
    page.fill('input[name="password"]', school_setup["admin_password"])
    page.click('button:has-text("Sign In")')
    expect(page.locator("#main-screen")).to_be_visible(timeout=5000)


def test_login_shows_dashboard(page: Page, base_url, school_setup):
    login_as_admin(page, base_url, school_setup)
    expect(page.locator("#page-title")).to_have_text("Dashboard")
    expect(page.locator("#brand-name")).to_have_text("Playwright Test School")


def test_school_name_change_updates_sidebar_immediately(page: Page, base_url, school_setup):
    """Regression test for the exact bug reported: sidebar showed stale
    school name after saving new settings, even though the DB was correct."""
    login_as_admin(page, base_url, school_setup)

    page.click("text=System Settings")
    expect(page.locator("h2:has-text('System Settings')")).to_be_visible()

    name_input = page.locator('input[name="name"]')
    name_input.fill("")
    name_input.fill("Renamed Academy")
    page.click('button:has-text("Save Settings")')

    # The success toast should appear...
    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)

    # ...and critically, the SIDEBAR (not just the form) must reflect the new name.
    expect(page.locator("#brand-name")).to_have_text("Renamed Academy", timeout=5000)


def test_school_name_persists_after_navigating_away_and_back(page: Page, base_url, school_setup):
    """Confirms the change was actually saved to the backend, not just
    held in local JS state — navigate to Dashboard and back to Settings."""
    login_as_admin(page, base_url, school_setup)

    page.click("text=System Settings")
    name_input = page.locator('input[name="name"]')
    name_input.fill("")
    name_input.fill("Persisted Academy")
    page.click('button:has-text("Save Settings")')
    expect(page.locator(".toast.success")).to_be_visible(timeout=5000)

    page.click("text=Dashboard")
    expect(page.locator("#brand-name")).to_have_text("Persisted Academy")

    page.click("text=System Settings")
    expect(page.locator('input[name="name"]')).to_have_value("Persisted Academy")


def test_logout_returns_to_login_screen(page: Page, base_url, school_setup):
    login_as_admin(page, base_url, school_setup)
    page.click("#btn-logout")
    expect(page.locator("#auth-screen")).to_be_visible(timeout=5000)
    expect(page.locator("#main-screen")).to_be_hidden()