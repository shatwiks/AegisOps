"""Explicit synthetic Alertmanager webhook fixture sender (test & demo utility only)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send an explicit synthetic signed Alertmanager webhook to AegisOps."
    )
    parser.add_argument("--service", default="eligibility-api")
    parser.add_argument("--namespace", default="aegisops-healthcare")
    parser.add_argument("--cluster", default="kind-aegisops-local")
    parser.add_argument("--alertname", default="SyntheticServiceDegraded")
    parser.add_argument("--severity", default="critical")
    parser.add_argument("--summary", default="Synthetic test alert from fixture CLI")
    parser.add_argument("--status", choices=["firing", "resolved"], default="firing")
    parser.add_argument(
        "--provenance",
        choices=["interactive_demo", "automated_test", "live_alert"],
        default="interactive_demo",
    )
    parser.add_argument(
        "--url", default="http://127.0.0.1:58000/api/v1/webhooks/alertmanager"
    )
    args = parser.parse_args()

    settings = get_settings()
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "receiver": "aegisops-synthetic-fixture",
        "status": args.status,
        "alerts": [
            {
                "status": args.status,
                "fingerprint": f"syn-{args.service}-{args.alertname}"[:32],
                "startsAt": now_iso,
                "labels": {
                    "alertname": args.alertname,
                    "severity": args.severity,
                    "service": args.service,
                    "namespace": args.namespace,
                    "cluster": args.cluster,
                },
                "annotations": {
                    "summary": args.summary,
                },
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        settings.aegisops_webhook_hmac_secret.encode("utf-8"),
        raw_bytes,
        hashlib.sha256,
    ).hexdigest()

    resp = httpx.post(
        args.url,
        content=raw_bytes,
        headers={
            "Content-Type": "application/json",
            "X-AegisOps-Signature": f"sha256={sig}",
            "X-AegisOps-Provenance": args.provenance,
        },
        timeout=10.0,
    )
    print(f"HTTP {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    main()
