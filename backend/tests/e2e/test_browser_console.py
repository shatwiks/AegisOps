"""Real Chromium Playwright E2E test for Keycloak OIDC PKCE login, topology, TOTP, and SRE Console."""

from __future__ import annotations

import os
import re

from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:55173"


def test_browser_oidc_pkce_login_topology_and_metrics() -> None:
    """Verify full browser OIDC PKCE login, React Flow topology, TOTP modal, and logout."""
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(FRONTEND_URL, wait_until="networkidle")
        assert page.get_by_text("Sign In with Keycloak OIDC (PKCE)").is_visible()
        page.get_by_role("button", name="Sign In with Keycloak OIDC (PKCE)").click()

        # Real Keycloak login form
        page.wait_for_selector("#username", timeout=15000)
        page.fill("#username", "approver@aegisops.local")
        page.fill("#password", demo_pw)
        page.click("#kc-login")

        # Redirect back to SRE Console after PKCE code exchange
        page.wait_for_selector("text=AegisOps SRE Console", timeout=15000)
        page.wait_for_selector("text=approver@aegisops.local (approver)", timeout=15000)
        page.wait_for_selector("text=CMDB Dependency & Blast-Radius Topology", timeout=15000)
        page.wait_for_selector("text=eligibility-api", timeout=15000)
        page.wait_for_selector("text=Stream: live", timeout=15000)

        # Open TOTP enrollment modal and generate QR
        page.get_by_role("button", name=re.compile(r"enroll totp mfa", re.I)).click()
        page.get_by_role("button", name="Generate TOTP QR Secret").click()
        page.wait_for_selector("text=Secret mask:", timeout=10000)
        page.get_by_role("button", name="Close").click()

        # Verify logout clears session
        page.get_by_role("button", name="Sign Out").click()
        page.wait_for_selector("text=Sign In with Keycloak OIDC (PKCE)", timeout=10000)
        browser.close()
