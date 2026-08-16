#!/usr/bin/env python3
"""Strip personal data out of a statement so it can be committed as a fixture.

    python scripts/anonymise_statement.py statement.xls --out fixture.xls
    python scripts/anonymise_statement.py statement.csv --out fixture.csv --jitter

Works on text-based statements (CSV, delimited `.xls` exports, TXT). PDFs are
**not** rewritten — a PDF's text layer, metadata and embedded fonts all carry
traces, and a tool that half-cleaned one would be worse than no tool at all.
For PDFs, generate a synthetic fixture instead; see any bank's
`tests/make_fixture.py` for a worked example.

⚠️ **Read the output before committing it.** This handles the patterns we know
about; it cannot recognise your name, your employer, or a distinctive spending
pattern. Statement layouts vary far too much for any tool to be exhaustive.

The safest fixture is one you invent rather than one you clean — see
docs/anonymising-statements.md.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Order matters: more specific patterns first, so an IFSC is not partially
# consumed by the generic long-digit rule.
REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "BANK0000000"),  # IFSC
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "ABCDE1234F"),  # PAN
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"), "test@example.com"),
    (
        re.compile(r"(?<![\d.])(?:\+?91[ -]?)?[6-9][0-9]{9}(?![\d.])"),
        "9000000000",
    ),
]

# Account and card numbers: keep the last four so parsers that match on them
# still have something to find.
LONG_DIGITS = re.compile(r"\b(?<![X*])(\d{9,18})\b")

# `\g<1>` rather than `\1`: a replacement like `\1000000000` would be read as
# group 10, which silently mangles the line.
LABELLED_FIELDS = [
    (
        re.compile(r"(?i)^(\s*(?:name|account holder|customer name)\s*[:\-]\s*).*$"),
        r"\g<1>TEST USER",
    ),
    (re.compile(r"(?i)^(\s*address\s*[:\-]\s*).*$"), r"\g<1>1 TEST STREET"),
    (re.compile(r"(?i)^(\s*city\s*[:\-]\s*).*$"), r"\g<1>TEST CITY"),
    (re.compile(r"(?i)^(\s*state\s*[:\-]\s*).*$"), r"\g<1>TEST STATE"),
    (re.compile(r"(?i)^(\s*(?:cust(?:omer)? id|crn)\s*[:\-]\s*).*$"), r"\g<1>000000000"),
]

# Matches both grouped (1,20,450.00) and ungrouped (120450.00) amounts — banks
# use both, sometimes in the same file.
AMOUNT = re.compile(r"\b\d[\d,]*\.\d{2}\b")

# Placeholders this tool has already substituted. Masking runs last, so without
# this it would turn its own 9000000000 into XXXXXX0000.
PLACEHOLDER_DIGITS = {"9000000000", "000000000"}


def mask_long_digits(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        digits = match.group(1)
        if digits in PLACEHOLDER_DIGITS or len(set(digits)) == 1:
            return digits
        return "X" * (len(digits) - 4) + digits[-4:]

    return LONG_DIGITS.sub(replace, text)


def jitter_amounts(text: str, seed: int = 0) -> str:
    """Scale every amount by a fixed random factor.

    A single factor for the whole file keeps running balances self-consistent,
    which matters because a parser test often checks them. Amounts are more
    identifying than people expect — a rent figure plus a salary credit narrows
    things down quickly.
    """
    rng = random.Random(seed)
    factor = Decimal(str(round(rng.uniform(0.6, 1.4), 3)))

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            return raw
        scaled = (value * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{scaled:,.2f}"

    return AMOUNT.sub(replace, text)


def anonymise(text: str, *, jitter: bool = False, seed: int = 0) -> str:
    for pattern, replacement in LABELLED_FIELDS:
        text = "\n".join(pattern.sub(replacement, line) for line in text.split("\n"))

    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)

    text = mask_long_digits(text)

    if jitter:
        text = jitter_amounts(text, seed=seed)

    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip personal data from a text-based bank statement.",
        epilog="Always read the output before committing it.",
    )
    parser.add_argument("source", type=Path, help="Statement to clean")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the result")
    parser.add_argument(
        "--jitter",
        action="store_true",
        help="Also scale all amounts by a fixed random factor",
    )
    parser.add_argument("--seed", type=int, default=0, help="Seed for --jitter")
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"No such file: {args.source}", file=sys.stderr)
        return 2

    if args.source.suffix.lower() == ".pdf" or args.source.read_bytes()[:5] == b"%PDF-":
        print(
            "This is a PDF, and this tool does not rewrite PDFs.\n\n"
            "A PDF carries personal data in its text layer, its metadata and "
            "sometimes its embedded fonts. A tool that cleaned only the visible "
            "text would give you false confidence.\n\n"
            "Generate a synthetic fixture instead — see any bank's "
            "tests/make_fixture.py, and docs/anonymising-statements.md.",
            file=sys.stderr,
        )
        return 2

    original = args.source.read_text(encoding="utf-8", errors="replace")
    cleaned = anonymise(original, jitter=args.jitter, seed=args.seed)
    args.out.write_text(cleaned, encoding="utf-8")

    changed = sum(1 for a, b in zip(original.split("\n"), cleaned.split("\n"), strict=False) if a != b)
    print(f"Wrote {args.out} ({changed} line(s) changed).")
    print("\nNow do these two things:")
    print(f"  1. Read {args.out} in full. This tool cannot recognise your name.")
    print("  2. Run: python scripts/check_fixtures_anonymised.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
