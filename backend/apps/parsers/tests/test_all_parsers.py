"""The shared parser test harness.

Every fixture under `apps/parsers/banks/*/tests/fixtures/` is discovered
automatically and checked against its golden file in `../expected/`. **A
contributor adding a bank writes no test code** — they add a fixture and a
golden file, and these tests start covering their parser.

Regenerate goldens after an intentional change, then read the diff:

    make regenerate-goldens BANK=hdfc
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from apps.parsers.base import BaseParser, Confidence, ParsedFile
from apps.parsers.registry import detect_parser, discover_parsers, rank_parsers
from apps.parsers.serialisation import statement_to_dict

BANKS_DIR = Path(__file__).resolve().parent.parent / "banks"


def _fixtures() -> list[tuple[str, Path, Path]]:
    """(bank_slug, fixture, golden) for every committed fixture."""
    found: list[tuple[str, Path, Path]] = []
    for bank_dir in sorted(BANKS_DIR.iterdir()):
        fixture_dir = bank_dir / "tests" / "fixtures"
        if not fixture_dir.is_dir():
            continue
        for fixture in sorted(fixture_dir.iterdir()):
            if fixture.is_file() and not fixture.name.startswith("."):
                golden = bank_dir / "tests" / "expected" / f"{fixture.stem}.json"
                found.append((bank_dir.name, fixture, golden))
    return found


FIXTURES = _fixtures()
FIXTURE_IDS = [f"{bank}/{fixture.name}" for bank, fixture, _ in FIXTURES]

pytestmark = pytest.mark.skipif(not FIXTURES, reason="no parser fixtures committed yet")


@pytest.mark.parametrize(("bank_slug", "fixture", "golden"), FIXTURES, ids=FIXTURE_IDS)
class TestFixtures:
    def test_detected_parser_belongs_to_this_bank(
        self, bank_slug: str, fixture: Path, golden: Path
    ) -> None:
        """Detection must route the fixture to the parser in its own directory.

        This is what stops a new bank from quietly hijacking another bank's
        statements — a failure here means two parsers claim the same file.
        """
        parser = detect_parser(ParsedFile(path=fixture))
        assert parser.bank_slug == bank_slug, (
            f"{fixture.name} was routed to {parser.bank_slug} "
            f"({parser.__name__}) but lives in banks/{bank_slug}/. "
            "Tighten can_parse() on one of them."
        )

    def test_matches_golden_file(self, bank_slug: str, fixture: Path, golden: Path) -> None:
        assert golden.exists(), (
            f"No golden file for {fixture.name}. Generate one with:\n"
            f"    make regenerate-goldens BANK={bank_slug}\n"
            "then read the output before committing it."
        )

        parser = detect_parser(ParsedFile(path=fixture))
        actual = statement_to_dict(parser().parse(ParsedFile(path=fixture)))
        expected = json.loads(golden.read_text())

        assert actual == expected, (
            f"{fixture.name} no longer parses to its golden file.\n"
            "If the change is intentional, run "
            f"`make regenerate-goldens BANK={bank_slug}` and review the diff."
        )

    def test_transactions_are_internally_consistent(
        self, bank_slug: str, fixture: Path, golden: Path
    ) -> None:
        """Invariants every parser must uphold, whatever the bank."""
        parser = detect_parser(ParsedFile(path=fixture))
        statement = parser().parse(ParsedFile(path=fixture))

        assert statement.transactions, "parsed a statement with no transactions"

        for transaction in statement.transactions:
            assert transaction.amount != 0, (
                f"zero-amount transaction on {transaction.txn_date} "
                f"({transaction.description!r}) — filter these out in the parser"
            )
            assert transaction.description.strip(), f"empty description on {transaction.txn_date}"

        if statement.period_start and statement.period_end:
            assert statement.period_start <= statement.period_end
            for transaction in statement.transactions:
                assert statement.period_start <= transaction.txn_date <= statement.period_end, (
                    f"transaction on {transaction.txn_date} falls outside the "
                    f"statement period {statement.period_start}..{statement.period_end}"
                )

    def test_source_hint_never_leaks_a_full_account_number(
        self, bank_slug: str, fixture: Path, golden: Path
    ) -> None:
        """A parser must not surface more than the last four digits."""
        parser = detect_parser(ParsedFile(path=fixture))
        hint = parser().parse(ParsedFile(path=fixture)).source_hint
        if hint is None:
            return
        digits = "".join(c for c in hint if c.isdigit())
        assert len(digits) <= 4, (
            f"source_hint {hint!r} exposes {len(digits)} digits. Mask all but " "the last four."
        )


class TestRegistry:
    def test_parsers_are_discovered(self) -> None:
        assert discover_parsers(), (
            "No parsers discovered. Each bank needs "
            "apps/parsers/banks/<bank>/parser.py with a BaseParser subclass."
        )

    def test_every_parser_declares_its_metadata(self) -> None:
        for parser in discover_parsers():
            assert parser.bank_slug, f"{parser.__name__} has no bank_slug"
            assert parser.display_name, f"{parser.__name__} has no display_name"
            assert parser.statement_kind in {"bank", "credit_card"}
            assert parser.file_formats, f"{parser.__name__} declares no file_formats"

    def test_bank_slug_matches_directory_name(self) -> None:
        """Keeps the registry navigable: banks/hdfc/ holds bank_slug "hdfc"."""
        for parser in discover_parsers():
            module_path = parser.__module__.split(".")
            directory = module_path[module_path.index("banks") + 1]
            assert parser.bank_slug == directory, (
                f"{parser.__name__} declares bank_slug={parser.bank_slug!r} "
                f"but lives in banks/{directory}/"
            )

    def test_unknown_file_is_rejected_with_a_helpful_message(self, tmp_path: Path) -> None:
        junk = tmp_path / "holiday-photo.csv"
        junk.write_text("this is not a bank statement at all\n")

        assert rank_parsers(ParsedFile(path=junk)) == []

        with pytest.raises(Exception, match="(?i)no parser recognised"):
            detect_parser(ParsedFile(path=junk))

    def test_empty_file_does_not_crash_detection(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        assert rank_parsers(ParsedFile(path=empty)) == []

    def test_a_throwing_can_parse_does_not_break_detection(self, monkeypatch, tmp_path) -> None:
        """One broken parser must not take the upload page down for every bank."""

        class Exploding(BaseParser):
            bank_slug = "exploding"
            display_name = "Exploding Bank"
            statement_kind = "bank"
            file_formats = ["csv"]

            @classmethod
            def can_parse(cls, file: ParsedFile) -> Confidence:
                raise RuntimeError("boom")

            def parse(self, file: ParsedFile):  # pragma: no cover - never reached
                raise NotImplementedError

        monkeypatch.setattr(
            "apps.parsers.registry.discover_parsers",
            lambda: (*discover_parsers(), Exploding),
        )

        junk = tmp_path / "unknown.csv"
        junk.write_text("nothing recognisable here\n")
        assert rank_parsers(ParsedFile(path=junk)) == []


@pytest.mark.skipif(
    os.environ.get("SKIP_FIXTURE_PRIVACY_CHECK") == "1",
    reason="explicitly skipped",
)
def test_fixtures_contain_no_obvious_personal_data() -> None:
    """The privacy scanner, run as part of the normal test suite.

    CI runs it separately too, but a contributor should find out before
    pushing, not after.
    """
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "check_fixtures_anonymised.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Test fixtures look like they contain personal data:\n\n"
        f"{result.stdout}\n{result.stderr}"
    )
