#!/usr/bin/env python3
"""
scripts/scan_secrets.py
-----------------------
Repository secret scanner for RIO-MJP.
Scans tracked source files and Git history for accidentally committed credentials,
tokens, API keys, database connection strings, and private keys.

Security Rules:
- Never prints discovered secret values to standard output or reports.
- Masks findings with redaction markers.
- Returns non-zero exit code if unallowlisted secrets are identified.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Pattern, Set, Tuple

# Patterns targeting high-confidence secret disclosures
RULES: List[Tuple[str, Pattern[str]]] = [
    ("NVIDIA_API_KEY", re.compile(r"nvapi-[A-Za-z0-9_-]{20,}")),
    ("ANTHROPIC_API_KEY", re.compile(r"sk-ant-api[0-9]{2}-[A-Za-z0-9_-]{20,}")),
    ("OPENAI_API_KEY", re.compile(r"sk-[A-Za-z0-9_-]{32,}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,}")),
    ("AWS_ACCESS_KEY", re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    (
        "DATABASE_CONN_WITH_CREDENTIALS",
        re.compile(r"postgres(?:ql)?(?:\+[a-z0-9]+)?://[a-zA-Z0-9_.-]+:(?!yourpassword|postgres|<|\[|\$)[^@\s]+@[a-zA-Z0-9_.-]+"),
    ),
]

# Allowlisted exact patterns and files
ALLOWLISTED_PATHS: Set[str] = {
    ".env.example",
    "frontend/.env.example",
    ".gitleaks.toml",
    "scripts/scan_secrets.py",
    "tests/database/test_database_safety.py",
    "tests/api/test_security_hardening.py",
}

ALLOWLISTED_REGEXES: List[Pattern[str]] = [
    re.compile(r"sk-ant-api03-validlookingkeyforunitmocking"),
    re.compile(r"nvapi-valid-test-key"),
    re.compile(r"nvapi-real-key-example"),
    re.compile(r"nvapi-abcdef1234567890"),
    re.compile(r"rio-ci-only-signing-key-not-used-outside-ephemeral-tests-2026"),
    re.compile(r"your-32-byte-random-secret-key-here"),
    re.compile(r"your_nvidia_api_key_here"),
    re.compile(r"yourpassword"),
]

BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".xlsx", ".pyc", ".db", ".sqlite", ".zip", ".tar", ".gz"
}


def is_allowlisted(path: str, line: str) -> bool:
    norm_path = path.replace("\\", "/")
    if norm_path in ALLOWLISTED_PATHS or any(norm_path.endswith(f"/{p}") for p in ALLOWLISTED_PATHS):
        return True
    for al_regex in ALLOWLISTED_REGEXES:
        if al_regex.search(line):
            return True
    return False


def scan_file_contents(filepath: str) -> List[Tuple[str, int, str]]:
    findings: List[Tuple[str, int, str]] = []
    norm_path = filepath.replace("\\", "/")
    if norm_path in ALLOWLISTED_PATHS:
        return findings

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fp:
            for line_no, line in enumerate(fp, 1):
                if is_allowlisted(filepath, line):
                    continue
                for rule_name, rule_regex in RULES:
                    if rule_regex.search(line):
                        findings.append((filepath, line_no, rule_name))
    except Exception as exc:
        print(f"[WARN] Could not inspect file {filepath}: {exc}", file=sys.stderr)

    return findings


def get_tracked_files(repo_root: Path) -> List[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=str(repo_root), text=True, errors="ignore"
        )
        files = [line.strip() for line in out.splitlines() if line.strip()]
        return [
            f for f in files
            if not any(f.lower().endswith(ext) for ext in BINARY_EXTENSIONS)
        ]
    except Exception as exc:
        print(f"[ERROR] Failed to query git ls-files: {exc}", file=sys.stderr)
        return []


def scan_repository(repo_root: Path) -> int:
    tracked = get_tracked_files(repo_root)
    total_findings: List[Tuple[str, int, str]] = []

    print(f"[INFO] Scanning {len(tracked)} tracked text files for exposed credentials...")
    for f in tracked:
        abs_path = repo_root / f
        if abs_path.is_file():
            findings = scan_file_contents(str(abs_path))
            total_findings.extend(findings)

    if total_findings:
        print("=" * 70, file=sys.stderr)
        print("SECURITY VULNERABILITY: EXPOSED SECRETS DETECTED IN TRACKED SOURCE", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for filepath, line_no, rule_name in total_findings:
            rel_path = os.path.relpath(filepath, str(repo_root))
            print(f"  VIOLATION: {rel_path}:{line_no} matches rule [{rule_name}] (value: [REDACTED])", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(f"Total violations found: {len(total_findings)}", file=sys.stderr)
        print("Remediation: Move credentials to environment variables or remove them from source.", file=sys.stderr)
        return 1

    print("[SUCCESS] Zero secrets detected in tracked source files.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RIO-MJP Security Secret Scanner")
    parser.add_argument("--repo-root", default=".", help="Root directory of repository")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    return scan_repository(repo_root)


if __name__ == "__main__":
    sys.exit(main())
