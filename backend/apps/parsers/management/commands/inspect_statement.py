"""Diagnose why a statement does or doesn't parse.

    python manage.py inspect_statement ~/Downloads/statement.pdf
    python manage.py inspect_statement statement.pdf --password 01011990
    python manage.py inspect_statement statement.pdf --lines 40

Nothing is written to the database and nothing is stored — the file is read and
reported on, then forgotten.

**Output is redacted by default** so it can be pasted into a bug report:
long digit runs, emails and card-shaped numbers are masked, and only a few
sample rows are shown. Pass `--raw` to see the unmasked text on your own
machine; do not paste that anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.parsers.base import ParsedFile, ParseError
from apps.parsers.registry import rank_parsers

REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), "<email>"),
    (re.compile(r"\b\d{9,18}\b"), "<long-number>"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "<pan>"),
    (re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)"), "<phone>"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class Command(BaseCommand):
    help = "Report how a statement file is detected and parsed, without storing anything"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("path", help="Path to the statement file")
        parser.add_argument("--password", help="For password-protected PDFs")
        parser.add_argument("--lines", type=int, default=25, help="Lines of extracted text to show")
        parser.add_argument("--rows", type=int, default=5, help="Sample transactions to show")
        parser.add_argument(
            "--raw",
            action="store_true",
            help="Do not redact. Local viewing only — never paste this output anywhere.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"No file at {path}")

        clean = (lambda text: text) if options["raw"] else redact
        file = ParsedFile(path=path, password=options.get("password"))

        self.stdout.write(self.style.MIGRATE_HEADING("\nFile"))
        self.stdout.write(f"  name       {path.name}")
        self.stdout.write(f"  size       {path.stat().st_size:,} bytes")
        self.stdout.write(f"  extension  {file.extension or '(none)'}")

        try:
            text = file.text
        except ParseError as exc:
            self.stdout.write(self.style.ERROR(f"\n  Could not read: {exc}"))
            self.stdout.write("\n  If this is a password-protected PDF, re-run with --password.")
            return

        self.stdout.write(f"  text layer {len(text):,} characters")
        if not text.strip():
            self.stdout.write(
                self.style.ERROR(
                    "\n  No text could be extracted. If this is a scan or a photo rather "
                    "than the file your bank sent, download the original — scanned "
                    "statements are not supported."
                )
            )
            return

        self.stdout.write(self.style.MIGRATE_HEADING("\nDetection"))
        ranked = rank_parsers(file)
        if not ranked:
            self.stdout.write(self.style.WARNING("  No parser recognised this file."))
        for parser, confidence in ranked:
            self.stdout.write(f"  {confidence.name:8} {parser.display_name} ({parser.bank_slug})")

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nFirst {options['lines']} lines"))
        for line in text.splitlines()[: options["lines"]]:
            self.stdout.write(f"  {clean(line)[:160]}")

        if not ranked:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Adding support for this bank is three files — see "
                    "docs/adding-a-bank-parser.md. The layout above is what a new "
                    "parser needs to read."
                )
            )
            return

        parser_class = ranked[0][0]
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nParsing with {parser_class.__name__}"))
        try:
            statement = parser_class().parse(file)
        except ParseError as exc:
            self.stdout.write(self.style.ERROR(f"  Failed: {exc}"))
            return
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Crashed: {type(exc).__name__}: {exc}"))
            self.stdout.write("  That is a bug — please report it with the layout above.")
            raise

        self.stdout.write(self.style.SUCCESS(f"  {len(statement.transactions)} transactions"))
        self.stdout.write(f"  period       {statement.period_start} to {statement.period_end}")
        self.stdout.write(f"  account      {statement.source_hint}")
        self.stdout.write(f"  opening      {statement.opening_balance}")
        self.stdout.write(f"  closing      {statement.closing_balance}")
        self.stdout.write(f"  total debits  {statement.total_debits}")
        self.stdout.write(f"  total credits {statement.total_credits}")

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nFirst {options['rows']} transactions"))
        for transaction in statement.transactions[: options["rows"]]:
            description = clean(transaction.description)[:46]
            self.stdout.write(
                f"  {transaction.txn_date}  {transaction.amount!s:>12}  {description}"
            )

        self.stdout.write(
            "\n  Check these against the statement itself: dates in the right order, "
            "amounts signed correctly (money out negative), and the closing balance "
            "matching.\n"
        )
