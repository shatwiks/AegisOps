"""Unit and adversarial tests for the PHI/PII/credential boundary scrubber."""

from __future__ import annotations

from app.privacy.scrubber import (
    evaluate_redaction_corpus,
    scrub_alertmanager_payload,
    scrub_text,
    scrub_value,
)


def test_scrub_text_positives_and_negatives() -> None:
    counts: dict[str, int] = {}
    dirty = (
        "Patient Name: Alice Henderson | SSN 123-45-6789 | MBR-90817263 | "
        "email=alice.henderson@example.org | ip=10.244.2.15 | "
        "Authorization: Bearer tok_super_secret_123456 | "
        "jwt=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.signature9988"
    )
    cleaned = scrub_text(dirty, counts)
    for sensitive in (
        "Alice Henderson",
        "123-45-6789",
        "MBR-90817263",
        "alice.henderson@example.org",
        "10.244.2.15",
        "tok_super_secret_123456",
        "eyJhbGciOiJSUzI1NiJ9",
    ):
        assert sensitive not in cleaned
    assert counts["ssn_dashed"] == 1
    assert counts["member_id"] == 1
    assert counts["email"] == 1
    assert counts["ipv4"] == 1
    assert counts["bearer"] == 1
    assert counts["jwt"] == 1
    assert counts["person_name"] == 1

    # Clean technical telemetry must remain intact
    clean_technical = "ERR_PG_POOL_TIMEOUT_57P03 image=aegisops/eligibility-api:v1.32.2 status=503"
    neg_counts: dict[str, int] = {}
    assert scrub_text(clean_technical, neg_counts) == clean_technical
    assert neg_counts == {}


def test_scrub_nested_mixed_case_and_multiline() -> None:
    payload = {
        "receiver": "aegisops",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "fingerprint": "fp-mixed-1",
                "startsAt": "2026-11-17T00:00:00Z",
                "labels": {
                    "alertname": "High5xxErrorRate",
                    "severity": "critical",
                    "service": "eligibility-api",
                    "PaTiEnT_NaMe": "Bob Builder",
                    "custom_unallowlisted_tag": "secret-val",
                },
                "annotations": {
                    "summary": "Line1\nMember: Bob Builder\nSSN: 987654321\nEmail: bob@health.test",
                    "Member-ID": "MEM_44556677",
                },
            }
        ],
    }
    res = scrub_alertmanager_payload(payload)
    assert not res.scrubber_failed_fallback
    alert = res.sanitized_data["alerts"][0]
    assert "patient_name" not in alert["labels"]
    assert "custom_unallowlisted_tag" not in alert["labels"]
    assert "member-id" not in alert["annotations"]
    assert res.dropped_unallowlisted_keys >= 1
    serialized = str(res.sanitized_data)
    assert "Bob Builder" not in serialized
    assert "987654321" not in serialized
    assert "bob@health.test" not in serialized
    assert "MEM_44556677" not in serialized


def test_scrub_value_recursive_dict_list() -> None:
    counts: dict[str, int] = {}
    nested = {
        "items": [
            {"Subscriber_Name": "Jane Doe", "note": "Reachable at 192.168.10.22"},
            "JWT eyJabcdefgh.eyJ12345678.signature_abc",
        ]
    }
    out = scrub_value(nested, counts)
    assert out["items"][0]["Subscriber_Name"] == "[REDACTED:SENSITIVE_FIELD]"
    assert "[REDACTED:IP]" in out["items"][0]["note"]
    assert "[REDACTED:JWT]" in out["items"][1]


def test_scrubber_fail_closed_never_forwards_raw_data() -> None:
    def boom() -> None:
        raise RuntimeError("regex engine crash")

    raw = {
        "alerts": [
            {
                "labels": {"alertname": "CrashTest", "service": "eligibility-api"},
                "annotations": {"summary": "RAW_SSN 123-45-6789 RAW_PATIENT John Smith"},
            }
        ]
    }
    res = scrub_alertmanager_payload(raw, _fault_hook=boom)
    assert res.scrubber_failed_fallback is True
    serialized = str(res.sanitized_data)
    assert "123-45-6789" not in serialized
    assert "John Smith" not in serialized
    assert res.sanitized_data["scrubber_status"] == "FAIL_CLOSED"


def test_redaction_corpus_benchmark() -> None:
    report = evaluate_redaction_corpus()
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0
    assert report["false_positives"] == 0
    assert report["false_negatives"] == 0
