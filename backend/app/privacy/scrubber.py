"""Earliest-boundary PHI/PII/credential scrubber and redaction corpus evaluator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Normalized lowercase keys (underscores/hyphens stripped) that are always redacted
SENSITIVE_KEY_TOKENS: frozenset[str] = frozenset(
    {
        "ssn",
        "socialsecuritynumber",
        "memberid",
        "subscriberid",
        "patientid",
        "patientname",
        "membername",
        "subscribername",
        "claimantname",
        "fullname",
        "firstname",
        "lastname",
        "dob",
        "dateofbirth",
        "birthdate",
        "email",
        "emailaddress",
        "phone",
        "phonenumber",
        "mrn",
        "medicalrecordnumber",
        "authorization",
        "authtoken",
        "bearertoken",
        "token",
        "jwt",
        "apikey",
        "secret",
        "password",
        "passwd",
        "cookie",
        "setcookie",
        "clientip",
        "remoteip",
        "sourceip",
    }
)

ALLOWED_ALERT_LABELS: frozenset[str] = frozenset(
    {
        "alertname",
        "severity",
        "service",
        "app",
        "namespace",
        "cluster",
        "instance",
        "pod",
        "deployment",
        "container",
        "env",
        "error_code",
        "component",
        "job",
    }
)

ALLOWED_ALERT_ANNOTATIONS: frozenset[str] = frozenset(
    {
        "summary",
        "description",
        "runbook_hint",
        "symptom",
    }
)

_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED:JWT]",
    ),
    (
        "bearer",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/=]{8,}"),
        "Bearer [REDACTED:TOKEN]",
    ),
    (
        "ssn_dashed",
        re.compile(r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"),
        "[REDACTED:SSN]",
    ),
    (
        "ssn_contextual",
        re.compile(r"(?i)\b(?:ssn|social[_\s-]?security)\s*[:=]\s*['\"]?\d{9}['\"]?"),
        "ssn=[REDACTED:SSN]",
    ),
    (
        "member_id",
        re.compile(r"(?i)\b(?:MBR|MEM|SUB|PAT|HICN|MBI|CLM)[-_:]?[A-Z0-9]{5,14}\b"),
        "[REDACTED:MEMBER_ID]",
    ),
    (
        "member_id_contextual",
        re.compile(
            r"(?i)\b(?:member_id|subscriber_id|patient_id|mrn)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{4,20}['\"]?"
        ),
        "member_id=[REDACTED:MEMBER_ID]",
    ),
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED:EMAIL]",
    ),
    (
        "ipv4",
        re.compile(
            r"(?<![.\d])(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?![.\d])"
        ),
        "[REDACTED:IP]",
    ),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
        "[REDACTED:PHONE]",
    ),
    (
        "dob",
        re.compile(
            r"(?i)\b(?:dob|date_of_birth|birth_date)\s*[:=]\s*['\"]?(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})['\"]?"
        ),
        "dob=[REDACTED:DOB]",
    ),
    (
        "person_name",
        re.compile(
            r"(?im)\b(?:patient|member|subscriber|claimant|beneficiary)(?:[_\s]+name)?\s*[:=]\s*['\"]?([A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){0,2})['\"]?"
        ),
        "person=[REDACTED:NAME]",
    ),
)


@dataclass
class ScrubResult:
    """Result of scrubbing an untrusted payload or string."""

    sanitized_data: Any
    redaction_counts: dict[str, int] = field(default_factory=dict)
    total_redactions: int = 0
    dropped_unallowlisted_keys: int = 0
    scrubber_failed_fallback: bool = False


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def scrub_text(text_value: str, counts: dict[str, int]) -> str:
    """Apply all deterministic redaction patterns to an arbitrary string."""
    result = text_value
    for category, pattern, replacement in _PATTERNS:
        result, n = pattern.subn(replacement, result)
        if n > 0:
            counts[category] = counts.get(category, 0) + n
    return result


def scrub_value(value: Any, counts: dict[str, int], *, key_hint: str | None = None) -> Any:
    """Recursively scrub strings, lists, and dictionaries."""
    if key_hint is not None and _normalize_key(key_hint) in SENSITIVE_KEY_TOKENS:
        counts["sensitive_field"] = counts.get("sensitive_field", 0) + 1
        return "[REDACTED:SENSITIVE_FIELD]"

    if isinstance(value, str):
        return scrub_text(value, counts)
    if isinstance(value, list):
        return [scrub_value(item, counts) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            sanitized[key_str] = scrub_value(v, counts, key_hint=key_str)
        return sanitized
    return value


def scrub_alertmanager_payload(
    payload: dict[str, Any],
    *,
    _fault_hook: Any | None = None,
) -> ScrubResult:
    """Scrub an Alertmanager webhook payload using an explicit field allowlist + deep redaction.

    Fail-closed: if scrubbing raises any error, returns a minimal safe event and flags
    scrubber_failed_fallback=True without ever forwarding raw payload fields.
    """
    counts: dict[str, int] = {}
    dropped = 0

    try:
        if _fault_hook is not None:
            _fault_hook()

        if not isinstance(payload, dict):
            raise TypeError("Alertmanager payload must be a JSON object")

        raw_alerts = payload.get("alerts", [])
        if not isinstance(raw_alerts, list):
            raise ValueError("Alertmanager 'alerts' field must be a list")

        clean_alerts: list[dict[str, Any]] = []
        for raw_alert in raw_alerts:
            if not isinstance(raw_alert, dict):
                continue

            raw_labels = raw_alert.get("labels") or {}
            clean_labels: dict[str, str] = {}
            if isinstance(raw_labels, dict):
                for lk, lv in raw_labels.items():
                    lk_lower = str(lk).strip().lower()
                    if _normalize_key(lk_lower) in SENSITIVE_KEY_TOKENS:
                        counts["sensitive_field"] = counts.get("sensitive_field", 0) + 1
                        continue
                    if lk_lower in ALLOWED_ALERT_LABELS:
                        clean_labels[lk_lower] = scrub_text(str(lv), counts)
                    else:
                        dropped += 1

            raw_ann = raw_alert.get("annotations") or {}
            clean_ann: dict[str, str] = {}
            if isinstance(raw_ann, dict):
                for ak, av in raw_ann.items():
                    ak_lower = str(ak).strip().lower()
                    if _normalize_key(ak_lower) in SENSITIVE_KEY_TOKENS:
                        counts["sensitive_field"] = counts.get("sensitive_field", 0) + 1
                        continue
                    if ak_lower in ALLOWED_ALERT_ANNOTATIONS:
                        clean_ann[ak_lower] = scrub_text(str(av), counts)
                    else:
                        dropped += 1

            clean_alerts.append(
                {
                    "status": str(raw_alert.get("status", "firing")).lower()[:32],
                    "fingerprint": scrub_text(str(raw_alert.get("fingerprint", ""))[:128], counts),
                    "startsAt": str(raw_alert.get("startsAt", ""))[:64],
                    "endsAt": str(raw_alert.get("endsAt", ""))[:64],
                    "labels": clean_labels,
                    "annotations": clean_ann,
                }
            )

        clean_payload = {
            "receiver": scrub_text(str(payload.get("receiver", "aegisops"))[:128], counts),
            "status": str(payload.get("status", "firing")).lower()[:32],
            "alerts": clean_alerts,
        }
        return ScrubResult(
            sanitized_data=clean_payload,
            redaction_counts=counts,
            total_redactions=sum(counts.values()),
            dropped_unallowlisted_keys=dropped,
            scrubber_failed_fallback=False,
        )
    except Exception:
        return ScrubResult(
            sanitized_data={
                "status": "firing",
                "scrubber_status": "FAIL_CLOSED",
                "alerts": [
                    {
                        "status": "firing",
                        "fingerprint": "scrubber-fallback",
                        "labels": {
                            "alertname": "SanitizerFallbackEscalation",
                            "severity": "critical",
                            "service": "unknown",
                        },
                        "annotations": {
                            "summary": "Alert payload quarantined because boundary scrubber failed",
                        },
                    }
                ],
            },
            redaction_counts={"fail_closed": 1},
            total_redactions=1,
            dropped_unallowlisted_keys=0,
            scrubber_failed_fallback=True,
        )


def evaluate_redaction_corpus() -> dict[str, Any]:
    """Run deterministic precision/recall benchmark on synthetic healthcare telemetry samples."""
    positives: list[tuple[str, str]] = [
        ("ssn_dashed", "Claim error for SSN 123-45-6789 on batch job"),
        ("ssn_contextual", "Failed validation ssn: 987654321 during intake"),
        ("member_id", "Timeout loading member MBR-90817263 from cache"),
        ("email", "Notification bounce to jane.q.member@example.org"),
        ("jwt", "Upstream header eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3OCJ9.sig12345678"),
        ("bearer", "Authorization: Bearer tok_live_987654321abcdef"),
        ("ipv4", "DB pool exhausted connecting from pod IP 10.244.1.42"),
        ("person_name", "Multiline log\nPatient Name: Alice Henderson\nstatus=503"),
        ("phone", "Callback failed for +1-555-234-5678"),
        ("dob", "Mismatch DOB=1984-07-19 in eligibility request"),
    ]
    negatives: list[str] = [
        "ERR_PG_POOL_TIMEOUT_57P03 pool_size=20 active=20 on eligibility-api",
        "Container claims-processor exited with code 137 OOMKilled on node kind-control-plane",
        "Release image aegisops/eligibility-api:v1.32.2 returned HTTP 503",
        "Deployment provider-directory scaled replicas=3 latency_p95=0.145s",
    ]

    true_positives = 0
    false_negatives = 0
    for expected_cat, sample in positives:
        counts: dict[str, int] = {}
        scrubbed = scrub_text(sample, counts)
        if "[REDACTED:" in scrubbed and expected_cat in counts:
            true_positives += 1
        else:
            false_negatives += 1

    false_positives = 0
    true_negatives = 0
    for clean_sample in negatives:
        counts = {}
        scrubbed = scrub_text(clean_sample, counts)
        if scrubbed == clean_sample and not counts:
            true_negatives += 1
        else:
            false_positives += 1

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives)
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives)
        else 0.0
    )

    return {
        "positive_samples": len(positives),
        "negative_samples": len(negatives),
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "false_positives": false_positives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "disclaimer": "Measured on synthetic test corpus; does not imply HIPAA or zero-leakage guarantee.",
    }
