#!/usr/bin/env python3
"""Scan parser test fixtures for personal data.

This is a backstop, not a guarantee. It catches the obvious misses — a PAN, an
Aadhaar-shaped number, an email address, a full account number — before they
become permanent git history. It cannot recognise a real person's name, and it
cannot read an encrypted PDF.

The actual safeguard is the contributor following docs/anonymising-statements.md.

Usage:
    python scripts/check_fixtures_anonymised.py [path ...]

Exits non-zero if anything suspicious is found.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SEARCH_PATHS = [
    REPO_ROOT / "backend" / "apps" / "parsers",
]

# Directories whose contents are treated as fixtures.
FIXTURE_DIR_NAMES = {"fixtures", "expected"}

# Values a properly anonymised fixture is expected to contain. Matches that are
# themselves placeholders are not findings.
ALLOWED_PLACEHOLDERS = {
    "test@example.com",
    "user@example.com",
    "noreply@example.com",
    "ABCDE1234F",  # canonical dummy PAN used in the anonymisation guide
    "XXXXXXXXXXXX",
}


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    hint: str


PATTERNS: list[Pattern] = [
    Pattern(
        "PAN",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "Replace with the dummy PAN ABCDE1234F.",
    ),
    Pattern(
        "Aadhaar-shaped number",
        re.compile(r"\b[2-9][0-9]{3}[ -]?[0-9]{4}[ -]?[0-9]{4}\b"),
        "Aadhaar numbers must never appear in the repository, masked or not.",
    ),
    Pattern(
        "Email address",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"),
        "Replace with test@example.com.",
    ),
    Pattern(
        "Indian mobile number",
        re.compile(r"(?<![\d.])(?:\+?91[ -]?)?[6-9][0-9]{9}(?![\d.])"),
        "Replace with 9000000000.",
    ),
    Pattern(
        "Unmasked account number",
        re.compile(r"\b(?<![X*])\d{11,18}\b"),
        "Mask all but the last four digits, e.g. XXXXXXXX1234.",
    ),
    Pattern(
        "IFSC code",
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        "Replace with a dummy such as BANK0000000.",
    ),
]


def iter_fixture_files(search_paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for base in search_paths:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if FIXTURE_DIR_NAMES.intersection(part for part in path.parts):
                files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    """Best-effort text extraction.

    Binary formats (PDF, XLS) still store plenty of plain-text runs, so a byte
    read with lossy decoding catches most leaks without a parsing dependency.
    """
    try:
        return path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return ""


def scan(path: Path) -> list[tuple[Pattern, str]]:
    text = read_text(path)
    findings: list[tuple[Pattern, str]] = []
    for pattern in PATTERNS:
        for match in pattern.regex.finditer(text):
            value = match.group(0)
            if value in ALLOWED_PLACEHOLDERS:
                continue
            findings.append((pattern, value))
    return findings


def main(argv: list[str]) -> int:
    search_paths = [Path(a).resolve() for a in argv[1:]] or DEFAULT_SEARCH_PATHS
    files = iter_fixture_files(search_paths)

    if not files:
        print("No fixture files found yet — nothing to scan.")
        return 0

    total = 0
    for path in files:
        findings = scan(path)
        if not findings:
            continue
        total += len(findings)
        rel = path.relative_to(REPO_ROOT)
        print(f"\n{rel}")
        seen: set[tuple[str, str]] = set()
        for pattern, value in findings:
            key = (pattern.name, value)
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{pattern.name}] {value}")
            print(f"      → {pattern.hint}")

    print(f"\nScanned {len(files)} fixture file(s).")
    if total:
        print(
            f"\nFound {total} potential leak(s) of personal data.\n"
            "Anonymise these before committing — see docs/anonymising-statements.md.\n"
            "If real data has already been pushed, report it privately per SECURITY.md\n"
            "rather than deleting it in a follow-up commit."
        )
        return 1

    print("No obvious personal data found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
