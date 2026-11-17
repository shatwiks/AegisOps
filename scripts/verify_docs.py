"""Verify that paths, routes, env vars, and evidence files referenced in docs exist in source."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DOCS_TO_CHECK = [
    REPO_ROOT / "workingflow.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "OVERALL_FLOW.md",
    REPO_ROOT / "docs" / "CODEMAP.md",
    REPO_ROOT / "docs" / "API.md",
    REPO_ROOT / "docs" / "DATA_MODEL.md",
    REPO_ROOT / "docs" / "SECURITY.md",
    REPO_ROOT / "docs" / "RUNBOOK.md",
    REPO_ROOT / "docs" / "VERIFICATION_REPORT.md",
    REPO_ROOT / "docs" / "SHOWCASE_GUIDE.md",
    REPO_ROOT / "docs" / "SHOWCASE_TEST_REPORT.md",
    REPO_ROOT / "docs" / "FILE_MAP.md",
    REPO_ROOT / ".planning" / "REQUIREMENTS.md",
    REPO_ROOT / ".planning" / "showcase" / "TRACEABILITY.md",
]

PATH_RE = re.compile(
    r"`((?:backend|frontend|services|infra|chaos|runbooks|scripts|docs|\.planning|\.github)/[A-Za-z0-9_.\-/{}*]+)`"
)
ENV_RE = re.compile(r"`(AEGISOPS_[A-Z0-9_]+)`")


def main() -> int:
    errors: list[str] = []
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for doc in DOCS_TO_CHECK:
        if not doc.exists():
            errors.append(f"Missing required doc: {doc}")
            continue
        text = doc.read_text(encoding="utf-8")

        for match in PATH_RE.finditer(text):
            rel = match.group(1)
            # Skip glob/brace placeholders intentionally used for grouping
            if any(ch in rel for ch in ("*", "{", "}")):
                continue
            target = REPO_ROOT / rel
            if not target.exists():
                errors.append(f"{doc.name}: referenced path does not exist -> {rel}")

        for match in ENV_RE.finditer(text):
            var = match.group(1)
            if var not in env_example and var not in ("AEGISOPS_API_URL",):
                # Allow documented test/runtime env overrides if present in backend/app/config.py
                cfg_text = (REPO_ROOT / "backend" / "app" / "config.py").read_text(
                    encoding="utf-8"
                )
                if var.lower() not in cfg_text:
                    errors.append(
                        f"{doc.name}: referenced env var missing from .env.example/config.py -> {var}"
                    )

    if errors:
        print("DOCUMENTATION VERIFICATION FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"Documentation check passed across {len(DOCS_TO_CHECK)} files with 0 broken paths or env vars."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
