"""Live end-to-end Kubernetes chaos scenario runner with control-interval persistence proofs."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pyotp
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from app.config import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPORT_PATH = _REPO_ROOT / "docs" / "evidence" / "chaos-scenarios-report.json"


async def _get_approver_token_and_totp(
    client: httpx.AsyncClient, settings: Any, api_url: str
) -> tuple[str, pyotp.TOTP]:
    pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    resp = await client.post(
        settings.aegisops_oidc_token_url,
        data={
            "grant_type": "password",
            "client_id": settings.aegisops_oidc_client_id,
            "username": "approver@aegisops.local",
            "password": pw,
            "scope": "openid profile email",
        },
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]

    enroll = await client.post(
        f"{api_url}/api/v1/auth/totp/enroll",
        headers={"Authorization": f"Bearer {token}"},
    )
    enroll.raise_for_status()
    uri = enroll.json()["provisioning_uri"]
    secret = pyotp.parse_uri(uri).secret
    totp = pyotp.TOTP(secret)

    # Activate enrollment with previous-tick OTP so current-tick OTP stays fresh for Scenario 1/4!
    from datetime import timedelta

    init_code = totp.at(datetime.now(UTC) - timedelta(seconds=30))
    ver = await client.post(
        f"{api_url}/api/v1/auth/totp/verify-enrollment",
        headers={"Authorization": f"Bearer {token}"},
        json={"otp_code": init_code},
    )
    ver.raise_for_status()
    return token, totp


def _patch_k8s_raw(deployment: str, body: dict[str, Any]) -> None:
    api_client = k8s_config.new_client_from_config(context="kind-aegisops-local")
    apps = k8s_client.AppsV1Api(api_client)
    apps.patch_namespaced_deployment(
        name=deployment, namespace="aegisops-healthcare", body=body
    )


def _wait_k8s_rollout_sync(deployment: str, timeout: int = 90) -> None:
    api_client = k8s_config.new_client_from_config(context="kind-aegisops-local")
    apps = k8s_client.AppsV1Api(api_client)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dep = apps.read_namespaced_deployment(
            name=deployment, namespace="aegisops-healthcare"
        )
        gen = dep.metadata.generation or 0
        obs_gen = dep.status.observed_generation or 0
        desired = dep.spec.replicas or 1
        total = dep.status.replicas or 0
        avail = dep.status.available_replicas or 0
        updated = dep.status.updated_replicas or 0
        ready = dep.status.ready_replicas or 0
        if (
            obs_gen >= gen
            and avail >= desired
            and updated >= desired
            and ready >= desired
            and total <= desired
        ):
            return
        time.sleep(2.0)
    raise TimeoutError(f"Rollout timeout for {deployment}")


async def _wait_for_incident(
    client: httpx.AsyncClient,
    api_url: str,
    token: str,
    *,
    alertname: str,
    service: str,
    since_iso: str,
    target_states: tuple[str, ...],
    timeout_sec: int = 150,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        r = await client.get(
            f"{api_url}/api/v1/incidents",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        for item in r.json()["items"]:
            if (
                item["alertname"] == alertname
                and item["asset_slug"] == service
                and item["ingested_at"] >= since_iso
                and item["state"] in target_states
            ):
                return dict(item)
        await asyncio.sleep(2.5)
    raise TimeoutError(
        f"Timed out waiting for {alertname} on {service} to reach {target_states}"
    )


async def _drive_traffic(
    url: str, stop_event: asyncio.Event, concurrency: int = 6
) -> None:
    async with httpx.AsyncClient(timeout=4.0) as client:

        async def _worker() -> None:
            while not stop_event.is_set():
                try:
                    await client.get(url, headers={"Connection": "close"})
                except Exception:
                    pass
                await asyncio.sleep(0.05)

        await asyncio.gather(*[_worker() for _ in range(concurrency)])


async def run_scenario_1(
    client: httpx.AsyncClient,
    api_url: str,
    token: str,
    totp: pyotp.TOTP,
    fault_token: str,
) -> dict[str, Any]:
    """Scenario 1: claims-processor memory pressure -> MFA-approved memory limit increase -> 60s recovery."""
    since = datetime.now(UTC).isoformat()
    # 1. Inject persistent 210MiB batch demand against 192Mi limit
    r = await client.post(
        "http://127.0.0.1:58082/internal/fault",
        headers={"X-Fault-Token": fault_token},
        json={"working_set_mb": 210},
    )
    r.raise_for_status()

    # 2. Control interval (15s): verify fault stays degraded without AegisOps action
    await asyncio.sleep(15)
    ctrl_probe = await client.get("http://127.0.0.1:58082/readyz")
    assert ctrl_probe.status_code == 503, (
        f"Expected control failure, got {ctrl_probe.status_code}"
    )

    # Drive /healthz scrapes to keep metrics flowing cleanly
    stop_traffic = asyncio.Event()
    traffic_task = asyncio.create_task(
        _drive_traffic("http://127.0.0.1:58082/healthz", stop_traffic, 2)
    )
    try:
        inc = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="ClaimsProcessorMemoryPressure",
            service="claims-processor",
            since_iso=since,
            target_states=("AWAITING_APPROVAL",),
            timeout_sec=120,
        )
        # Wait until OTP tick is strictly newer than last used if needed and approve
        detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{inc['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        pending = next(a for a in detail["approvals"] if a["status"] == "PENDING")

        # Wait up to 31s if same 30s timecode was just consumed
        for _ in range(35):
            appr = await client.post(
                f"{api_url}/api/v1/incidents/{inc['id']}/approve",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "otp_code": totp.now(),
                    "expected_playbook_id": pending["playbook_id"],
                    "expected_target_slug": pending["target_asset_slug"],
                    "expected_parameters_hash": pending["parameters_hash"],
                    "reason": "Chaos Scenario 1 SRE approval for memory_limit_increase_bounded (384Mi)",
                },
            )
            if appr.status_code == 200:
                break
            await asyncio.sleep(2.0)
        assert appr.status_code == 200, appr.text

        resolved = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="ClaimsProcessorMemoryPressure",
            service="claims-processor",
            since_iso=since,
            target_states=("RESOLVED",),
            timeout_sec=300,
        )
        final_detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{resolved['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        return {
            "scenario": "1_claims_processor_memory_pressure",
            "control_interval_probe_status": ctrl_probe.status_code,
            "incident": final_detail["incident"],
            "executions": final_detail["executions"],
        }
    finally:
        stop_traffic.set()
        await traffic_task
        # Cleanup: restore batch demand to 64MiB and Deployment limit to 192Mi
        await client.post(
            "http://127.0.0.1:58082/internal/fault",
            headers={"X-Fault-Token": fault_token},
            json={"working_set_mb": 64},
        )
        _patch_k8s_raw(
            "claims-processor",
            {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "claims-processor",
                                    "resources": {
                                        "limits": {"memory": "192Mi"},
                                        "requests": {"memory": "96Mi"},
                                    },
                                }
                            ]
                        }
                    }
                }
            },
        )
        _wait_k8s_rollout_sync("claims-processor")


async def run_scenario_2(
    client: httpx.AsyncClient, api_url: str, token: str, fault_token: str
) -> dict[str, Any]:
    """Scenario 2: eligibility-api DB pool exhaustion -> autonomous restart -> 60s recovery."""
    since = datetime.now(UTC).isoformat()
    r = await client.post(
        "http://127.0.0.1:58081/internal/fault",
        headers={"X-Fault-Token": fault_token},
        json={"db_pool_exhausted": True},
    )
    r.raise_for_status()

    # Control interval (15s): verify pool exhaustion does NOT self-heal
    await asyncio.sleep(15)
    ctrl_probe = await client.get("http://127.0.0.1:58081/api/eligibility/check")
    assert ctrl_probe.status_code == 503

    stop_traffic = asyncio.Event()
    traffic_task = asyncio.create_task(
        _drive_traffic("http://127.0.0.1:58081/api/eligibility/check", stop_traffic, 3)
    )
    try:
        resolved = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="EligibilityDbPoolExhausted",
            service="eligibility-api",
            since_iso=since,
            target_states=("RESOLVED",),
            timeout_sec=300,
        )
        final_detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{resolved['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        return {
            "scenario": "2_eligibility_db_pool_exhaustion",
            "control_interval_probe_status": ctrl_probe.status_code,
            "incident": final_detail["incident"],
            "executions": final_detail["executions"],
        }
    finally:
        stop_traffic.set()
        await traffic_task


async def run_scenario_3(
    client: httpx.AsyncClient, api_url: str, token: str, fault_token: str
) -> dict[str, Any]:
    """Scenario 3: provider-directory sustained CPU/load pressure -> autonomous scale-out (3 replicas) -> 60s recovery."""
    since = datetime.now(UTC).isoformat()
    r = await client.post(
        "http://127.0.0.1:58083/internal/fault",
        headers={"X-Fault-Token": fault_token},
        json={"cpu_pressure_active": True},
    )
    r.raise_for_status()

    stop_traffic = asyncio.Event()
    # 6 concurrent callers saturate 1 pod (2 slots -> ~0.66s > 0.50s), whereas 3 pods (6 slots) keep p95 <= 0.44s
    traffic_task = asyncio.create_task(
        _drive_traffic("http://127.0.0.1:58083/api/providers/search", stop_traffic, 6)
    )
    try:
        await asyncio.sleep(15)
        t0 = time.perf_counter()
        ctrl_resp = await client.get("http://127.0.0.1:58083/api/providers/search")
        ctrl_latency = round(time.perf_counter() - t0, 3)
        assert ctrl_resp.status_code == 200

        resolved = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="ProviderDirectoryHighLatencyCpu",
            service="provider-directory",
            since_iso=since,
            target_states=("RESOLVED",),
            timeout_sec=300,
        )
        final_detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{resolved['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        return {
            "scenario": "3_provider_directory_cpu_load_scale_out",
            "control_interval_probe_latency_sec": ctrl_latency,
            "incident": final_detail["incident"],
            "executions": final_detail["executions"],
        }
    finally:
        stop_traffic.set()
        await traffic_task
        await client.post(
            "http://127.0.0.1:58083/internal/fault",
            headers={"X-Fault-Token": fault_token},
            json={"cpu_pressure_active": False},
        )
        _patch_k8s_raw("provider-directory", {"spec": {"replicas": 1}})
        _wait_k8s_rollout_sync("provider-directory")


async def run_scenario_4(
    client: httpx.AsyncClient, api_url: str, token: str, totp: pyotp.TOTP
) -> dict[str, Any]:
    """Scenario 4: unhealthy canary image release -> MFA-approved rollback -> 60s recovery."""
    since = datetime.now(UTC).isoformat()
    _patch_k8s_raw(
        "eligibility-api",
        {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "eligibility-api",
                                "image": "aegisops/eligibility-api:v1.9.0-broken",
                            }
                        ]
                    }
                }
            }
        },
    )
    _wait_k8s_rollout_sync("eligibility-api")
    stop_traffic = asyncio.Event()
    traffic_task = asyncio.create_task(
        _drive_traffic("http://127.0.0.1:58081/api/eligibility/check", stop_traffic, 4)
    )
    try:
        await asyncio.sleep(15)
        ctrl_probe = await client.get("http://127.0.0.1:58081/api/eligibility/check")
        assert ctrl_probe.status_code == 500

        inc = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="High5xxErrorRate",
            service="eligibility-api",
            since_iso=since,
            target_states=("AWAITING_APPROVAL",),
            timeout_sec=120,
        )
        detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{inc['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        pending = next(a for a in detail["approvals"] if a["status"] == "PENDING")

        for _ in range(35):
            appr = await client.post(
                f"{api_url}/api/v1/incidents/{inc['id']}/approve",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "otp_code": totp.now(),
                    "expected_playbook_id": pending["playbook_id"],
                    "expected_target_slug": pending["target_asset_slug"],
                    "expected_parameters_hash": pending["parameters_hash"],
                    "reason": "Chaos Scenario 4 SRE MFA approval for known-good image rollback",
                },
            )
            if appr.status_code == 200:
                break
            await asyncio.sleep(2.0)
        assert appr.status_code == 200, appr.text

        resolved = await _wait_for_incident(
            client,
            api_url,
            token,
            alertname="High5xxErrorRate",
            service="eligibility-api",
            since_iso=since,
            target_states=("RESOLVED",),
            timeout_sec=300,
        )
        final_detail = (
            await client.get(
                f"{api_url}/api/v1/incidents/{resolved['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()
        return {
            "scenario": "4_bad_canary_image_mfa_rollback",
            "control_interval_probe_status": ctrl_probe.status_code,
            "incident": final_detail["incident"],
            "executions": final_detail["executions"],
        }
    finally:
        stop_traffic.set()
        await traffic_task


async def main_async(scenario_arg: str) -> None:
    settings = get_settings()
    api_url = f"http://{settings.aegisops_api_host}:{settings.aegisops_api_port}"
    fault_token = os.environ["DEMO_INTERNAL_FAULT_TOKEN"]

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        token, totp = await _get_approver_token_and_totp(client, settings, api_url)
        if scenario_arg in ("all", "1"):
            print(
                "[Chaos] Running Scenario 1 (claims-processor memory pressure -> MFA approval)..."
            )
            results.append(
                await run_scenario_1(client, api_url, token, totp, fault_token)
            )
        if scenario_arg in ("all", "2"):
            print(
                "[Chaos] Running Scenario 2 (eligibility-api DB pool exhaustion -> autonomous restart)..."
            )
            results.append(await run_scenario_2(client, api_url, token, fault_token))
        if scenario_arg in ("all", "3"):
            print(
                "[Chaos] Running Scenario 3 (provider-directory load pressure -> autonomous scale-out)..."
            )
            results.append(await run_scenario_3(client, api_url, token, fault_token))
        if scenario_arg in ("all", "4"):
            print(
                "[Chaos] Running Scenario 4 (eligibility-api broken canary -> MFA rollback)..."
            )
            results.append(await run_scenario_4(client, api_url, token, totp))

        metrics_resp = await client.get(
            f"{api_url}/api/v1/metrics/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        metrics_resp.raise_for_status()

    report = {
        "executed_at": datetime.now(UTC).isoformat(),
        "recovery_window_seconds": settings.aegisops_recovery_window_seconds,
        "scenarios": results,
        "measured_metrics_summary": metrics_resp.json(),
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"[Chaos] All selected scenarios PASSED and resolved cleanly. Report saved to {_REPORT_PATH}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute AegisOps live Kubernetes chaos scenarios."
    )
    parser.add_argument(
        "--scenario", default="all", choices=["all", "1", "2", "3", "4"]
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.scenario))


if __name__ == "__main__":
    main()
