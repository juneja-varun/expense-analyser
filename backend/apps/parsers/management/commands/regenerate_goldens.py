"""Regenerate golden files for parser fixtures.

    python manage.py regenerate_goldens             # every bank
    python manage.py regenerate_goldens --bank hdfc
    python manage.py regenerate_goldens --check     # what CI effectively asserts

**Always read the diff before committing.** A golden file records what the
parser currently does, not what it should do — regenerating without reading is
how a parsing bug becomes the expected behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.parsers.base import ParsedFile
from apps.parsers.registry import detect_parser
from apps.parsers.serialisation import statement_to_json

# commands/ -> management/ -> parsers/
BANKS_DIR = Path(__file__).resolve().parents[2] / "banks"


class Command(BaseCommand):
    help = "Regenerate golden files for bank parser fixtures"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--bank", help="Only this bank slug (default: all)")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report differences without writing anything",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        bank = options.get("bank")
        check_only = options.get("check", False)

        bank_dirs = sorted(d for d in BANKS_DIR.iterdir() if d.is_dir())
        if bank:
            bank_dirs = [d for d in bank_dirs if d.name == bank]
            if not bank_dirs:
                raise CommandError(f"No bank directory named {bank!r} under {BANKS_DIR}")

        written = unchanged = failed = 0

        for bank_dir in bank_dirs:
            fixture_dir = bank_dir / "tests" / "fixtures"
            expected_dir = bank_dir / "tests" / "expected"
            if not fixture_dir.is_dir():
                continue
            expected_dir.mkdir(parents=True, exist_ok=True)

            for fixture in sorted(fixture_dir.iterdir()):
                if not fixture.is_file() or fixture.name.startswith("."):
                    continue

                golden = expected_dir / f"{fixture.stem}.json"
                label = f"{bank_dir.name}/{fixture.name}"

                try:
                    parser = detect_parser(ParsedFile(path=fixture))
                    payload = statement_to_json(parser().parse(ParsedFile(path=fixture)))
                except Exception as exc:
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"  FAIL  {label}: {exc}"))
                    continue

                if golden.exists() and golden.read_text() == payload:
                    unchanged += 1
                    self.stdout.write(f"  same  {label}")
                    continue

                if check_only:
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"  DIFF  {label}"))
                    self._show_diff(golden, payload)
                    continue

                golden.write_text(payload)
                written += 1
                verb = "update" if golden.exists() else "create"
                self.stdout.write(self.style.SUCCESS(f"  {verb}  {label}"))

        summary = f"{unchanged} unchanged, {written} written, {failed} failed"
        if failed:
            raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
        if written and not check_only:
            self.stdout.write(
                self.style.WARNING(
                    "\nRead the diff before committing — a golden file records what "
                    "the parser does, not what it should do."
                )
            )

    def _show_diff(self, golden: Path, payload: str) -> None:
        import difflib

        old = golden.read_text().splitlines() if golden.exists() else []
        diff = difflib.unified_diff(
            old, payload.splitlines(), fromfile=str(golden), tofile="(generated)", lineterm=""
        )
        for line in list(diff)[:40]:
            self.stderr.write(f"    {line}")

    @staticmethod
    def _load(path: Path) -> Any:
        return json.loads(path.read_text()) if path.exists() else None
