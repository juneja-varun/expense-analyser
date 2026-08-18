"""Parser discovery and dispatch.

Parsers are found by walking `apps/parsers/banks/`. There is deliberately no
list of parsers anywhere: adding a bank means adding a directory, so two people
adding different banks never touch the same file and never conflict.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from functools import cache
from pathlib import Path

from apps.parsers.base import BaseParser, Confidence, NoParserFound, ParsedFile, ParsedStatement

logger = logging.getLogger(__name__)

MIN_AUTO_DETECT = Confidence.LIKELY
"""Confidence required to parse a file without asking the user.

WEAK means "plausible shape, no positive identification" — and acting on that
is worse than refusing. A statement routed to the wrong parser does not fail
loudly; it produces confident, wrong numbers (an ICICI savings statement handed
to the credit-card parser read the closing balance as the transaction amount).
Below this bar the user picks the bank.
"""

BANKS_PACKAGE = "apps.parsers.banks"
BANKS_DIR = Path(__file__).parent / "banks"

__all__ = [
    "detect_parser",
    "discover_parsers",
    "get_parser",
    "get_parsers",
    "parse_statement",
    "rank_parsers",
    "supported_banks",
]


@cache
def discover_parsers() -> tuple[type[BaseParser], ...]:
    """Every concrete parser under `banks/`.

    Cached: the filesystem walk happens once per process. Call
    `discover_parsers.cache_clear()` in tests that add parsers at runtime.
    """
    parsers: list[type[BaseParser]] = []

    if not BANKS_DIR.exists():
        return ()

    for module_info in pkgutil.walk_packages([str(BANKS_DIR)], prefix=f"{BANKS_PACKAGE}."):
        if not module_info.name.endswith(".parser"):
            continue
        try:
            module = importlib.import_module(module_info.name)
        except Exception:
            # One broken parser must not take down every other bank — the
            # upload page should still work for everyone else.
            logger.exception("Could not import parser module %s", module_info.name)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseParser)
                and obj is not BaseParser
                and not inspect.isabstract(obj)
                and obj.__module__ == module_info.name
            ):
                parsers.append(obj)

    _check_for_duplicates(parsers)
    return tuple(sorted(parsers, key=lambda p: (p.bank_slug, p.statement_kind)))


def _check_for_duplicates(parsers: list[type[BaseParser]]) -> None:
    seen: dict[tuple[str, str], type[BaseParser]] = {}
    for parser in parsers:
        key = (parser.bank_slug, parser.statement_kind)
        if key in seen:
            raise RuntimeError(
                f"Two parsers claim {key[0]}/{key[1]}: "
                f"{seen[key].__name__} and {parser.__name__}. "
                "Each bank and statement kind needs a distinct pair."
            )
        seen[key] = parser


def get_parsers() -> tuple[type[BaseParser], ...]:
    return discover_parsers()


def get_parser(bank_slug: str, statement_kind: str | None = None) -> type[BaseParser]:
    """Look up a parser explicitly — used when the user picks their bank."""
    for parser in discover_parsers():
        if parser.bank_slug == bank_slug and (
            statement_kind is None or parser.statement_kind == statement_kind
        ):
            return parser
    raise NoParserFound(f"No parser registered for {bank_slug}/{statement_kind or 'any'}")


def rank_parsers(file: ParsedFile) -> list[tuple[type[BaseParser], Confidence]]:
    """All parsers that recognise the file at all, best first.

    Exposed so the UI can offer the runners-up when detection is uncertain.
    """
    scored: list[tuple[type[BaseParser], Confidence]] = []
    for parser in discover_parsers():
        if not parser.handles_extension(file):
            continue
        try:
            confidence = parser.can_parse(file)
        except Exception:
            # can_parse runs against arbitrary uploads; a parser that throws on
            # a malformed file should be skipped, not break detection.
            logger.exception("can_parse failed for %s", parser.__name__)
            continue
        if confidence > Confidence.NONE:
            scored.append((parser, confidence))

    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def detect_parser(file: ParsedFile) -> type[BaseParser]:
    """The best parser for this file.

    Raises NoParserFound if nothing recognises it, or if the top two candidates
    tie — an ambiguous guess is worse than asking the user which bank it is.
    """
    ranked = rank_parsers(file)

    if not ranked:
        raise NoParserFound(
            f"No parser recognised {file.filename}. If your bank isn't supported yet, "
            "see docs/adding-a-bank-parser.md — or open a bank support request."
        )

    best, confidence = ranked[0]
    if confidence < MIN_AUTO_DETECT:
        names = ", ".join(f"{p.display_name}" for p, _ in ranked[:3])
        raise NoParserFound(
            f"{file.filename} looks like it might be from {names}, but not clearly "
            "enough to be sure. Please pick the bank manually — guessing risks "
            "importing the wrong numbers."
        )

    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        names = ", ".join(p.display_name for p, _ in ranked[:3])
        raise NoParserFound(
            f"Could not tell which bank {file.filename} is from — it matches "
            f"{names} equally well. Please pick the bank manually."
        )

    return ranked[0][0]


def parse_statement(file: ParsedFile, bank_slug: str | None = None) -> ParsedStatement:
    """Parse an uploaded statement.

    Pass `bank_slug` when the user has told us which bank it is; otherwise the
    parser is detected from the file.
    """
    parser_class = get_parser(bank_slug) if bank_slug else detect_parser(file)
    return parser_class().parse(file)


def supported_banks() -> list[dict[str, object]]:
    """Registered parsers, for the README table and the upload UI."""
    return [
        {
            "bank_slug": parser.bank_slug,
            "display_name": parser.display_name,
            "statement_kind": parser.statement_kind,
            "file_formats": list(parser.file_formats),
        }
        for parser in discover_parsers()
    ]
