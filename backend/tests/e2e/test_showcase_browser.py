"""End-to-end Playwright Chromium tests for AegisOps Showcase journeys (Visitor, Replay, Privacy, RAG, Evidence & Operator)."""

from __future__ import annotations

import os
import time

import httpx
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:55173"
API_READY_URL = "http://127.0.0.1:58000/readyz"


def _wait_api_ready() -> None:
    for _ in range(30):
        try:
            r = httpx.get(API_READY_URL, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("FastAPI backend on 127.0.0.1:58000 did not become ready in time")


def test_showcase_visitor_replay_knowledge_evidence_and_operator_flows() -> None:
    """Verify full Visitor Mode, Guided Replay, Privacy Playground, Hybrid Search, Evidence & Operator console in Chromium."""
    _wait_api_ready()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # 1. Visitor Mode Landing (unauthenticated, immediate access without login wall)
        page.goto(FRONTEND_URL, wait_until="networkidle")
        page.wait_for_selector("text=Visitor Mode (Read-Only)", timeout=15000)
        page.wait_for_selector("text=Sign In with Keycloak OIDC (PKCE)", timeout=10000)
        page.wait_for_selector("text=Chaos Lab & Self-Healing Scenarios (5 Scenarios)", timeout=10000)
        page.wait_for_selector("text=Baseline not configured", timeout=10000)
        page.wait_for_selector("text=ready /", timeout=10000)

        # Toggle Accessible Topology Table View & back
        page.get_by_role("button", name="Accessible Table View").click()
        page.wait_for_selector("text=Live K8s Replicas & Image", timeout=5000)
        page.get_by_role("button", name="Graph View").click()

        # 2. Guided Tour over Recorded Replay (`visitor+`)
        page.get_by_role("button", name="Start Guided Demo (Recorded Replay)").click()
        page.wait_for_selector("text=RECORDED REPLAY — No live cluster changes", timeout=10000)
        page.wait_for_selector("text=GUIDED TOUR (RECORDED REPLAY)", timeout=10000)
        page.get_by_role("button", name="Step Forward ▶").click()
        page.wait_for_selector("text=Frame 2/", timeout=5000)
        page.get_by_role("button", name="Exit Replay -> Return to Live View").click()

        # 3. Knowledge Base, Privacy Scrubber Playground & Hybrid Search Tester
        page.get_by_role("button", name="Knowledge Base & Privacy Playground").click()
        page.wait_for_selector("text=Edge Privacy Scrubber Playground", timeout=10000)
        page.get_by_role("button", name="Test Privacy Scrubber").click()
        page.wait_for_selector("text=[REDACTED:SSN]", timeout=10000)

        page.get_by_role("button", name="Test Hybrid Search").click()
        page.wait_for_selector("text=rb-002-eligibility-db-pool-exhaustion", timeout=10000)
        page.wait_for_selector("text=PASS", timeout=10000)

        # 4. Engineering Evidence Page
        page.get_by_role("button", name="Engineering Evidence").click()
        page.wait_for_selector("text=Running Build & Environment Metadata", timeout=10000)
        page.wait_for_selector("text=Ragas Offline LLM Evaluation", timeout=10000)
        page.wait_for_selector("text=k6 Webhook Burst & Idempotency Benchmark", timeout=10000)

        # 5. Return to Operations Console & authenticate as Operator via real Keycloak OIDC PKCE
        page.get_by_role("button", name="Operations Console").click()
        page.get_by_role("button", name="Sign In with Keycloak OIDC (PKCE)").click()
        page.wait_for_selector("#username", timeout=15000)
        page.fill("#username", "operator@aegisops.local")
        page.fill("#password", demo_pw)
        page.click("#kc-login")

        page.wait_for_selector("text=AegisOps SRE Console", timeout=15000)
        page.wait_for_selector("text=operator@aegisops.local (operator)", timeout=15000)
        page.wait_for_selector("text=Hide Test Runs", timeout=10000)

        # Trigger live Business Transaction Recovery Probe (Check Patient Eligibility)
        page.get_by_role("button", name="Check Patient Eligibility").click()
        page.wait_for_selector("text=Synthetic eligibility check passed", timeout=10000)

        # Toggle Executive vs Technical view & open Readiness breakdown + Restore Demo Baseline Preview Modal
        page.get_by_role("button", name="View: Executive Overview").click()
        page.wait_for_selector("text=View: Technical Deep-Dive", timeout=5000)
        page.get_by_role("button", name="Restore Demo Baseline").click()
        page.wait_for_selector("text=Restore Demo Baseline — Concrete Preview", timeout=10000)
        page.get_by_role("button", name="Close").click()

        page.get_by_role("button", name="Sign Out").click()
        page.wait_for_selector("text=Sign In with Keycloak OIDC (PKCE)", timeout=10000)

        assert not page_errors, f"Uncaught page errors: {page_errors}"
        # Allow benign 401 from /api/v1/auth/me probe when intentionally unauthenticated
        real_console_errs = [e for e in console_errors if "401" not in e]
        assert not real_console_errs, f"Console errors observed: {real_console_errs}"
        browser.close()
