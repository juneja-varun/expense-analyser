"""The parser contract.

Everything a bank parser needs is here. Parsers take a file and return
dataclasses — they never touch the database, which keeps them unit-testable and
means you need no Django knowledge to write one.

To add a bank, see docs/adding-a-bank-parser.md.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

StatementKind = Literal["bank", "credit_card"]


class ParseError(Exception):
    """Raised when a parser recognises a file but cannot read it.

    The message is shown to the user, so say what went wrong and what they can
    do about it — "password required", not "IndexError at line 40".
    """


class NoParserFound(ParseError):
    """No registered parser recognised the file."""


class Confidence(enum.IntEnum):
    """How sure a parser is that a file belongs to it.

    A score rather than a boolean, because several banks produce similar
    layouts. The dispatcher takes the highest scorer and, when nothing is
    confident, asks the user which bank it is — silently mis-parsing a
    statement is worse than failing to parse it.
    """

    NONE = 0
    """Definitely not ours."""

    WEAK = 25
    """Plausible shape, no positive identification. E.g. a bare CSV whose
    columns look right but which carries no bank name."""

    LIKELY = 60
    """Bank identified, but the specific statement type is inferred."""

    STRONG = 90
    """Bank and statement type both positively identified."""

    CERTAIN = 100
    """An unambiguous marker — an account-number format or document ID that no
    other issuer uses."""


@dataclass(frozen=True)
class ParsedTransaction:
    """One row of a statement, normalised.

    `amount` is signed: **negative is money leaving the account**. Card
    statements often present spends as positive and payments as credits;
    normalise that in the parser so downstream code never has to care which
    kind of statement a transaction came from.
    """

    txn_date: date
    description: str
    """The narration exactly as printed. Never clean this up — the user needs
    to recognise their own transaction, and the categorisation rules match on
    the raw string."""

    amount: Decimal
    value_date: date | None = None
    balance: Decimal | None = None
    reference: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    """The original row, kept for debugging a mis-parse."""

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"amount must be Decimal, got {type(self.amount).__name__}. "
                "Floats lose precision on money — use utils.amounts.parse_amount()."
            )


@dataclass(frozen=True)
class ParsedStatement:
    """The result of parsing one statement file."""

    transactions: list[ParsedTransaction]
    source_hint: str | None = None
    """Masked account or card number, if the statement prints one. Used to
    match the upload to an existing account without the user picking it."""

    period_start: date | None = None
    period_end: date | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    bank_slug: str = ""
    statement_kind: str = ""

    @property
    def total_debits(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.amount < 0), Decimal("0"))

    @property
    def total_credits(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.amount > 0), Decimal("0"))


@dataclass
class ParsedFile:
    """An uploaded file, with lazily-decoded views of its contents.

    Parsers receive one of these rather than a path so that `can_parse` can
    sniff cheaply: the text of a PDF is extracted at most once per upload, no
    matter how many parsers inspect it.
    """

    path: Path
    filename: str = ""
    password: str | None = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.filename:
            self.filename = self.path.name

    @property
    def extension(self) -> str:
        """Lowercase extension without the dot."""
        return self.path.suffix.lower().lstrip(".")

    @cached_property
    def content(self) -> bytes:
        return self.path.read_bytes()

    @cached_property
    def text(self) -> str:
        """The file decoded as text.

        For PDFs this is the extracted text layer; for everything else the raw
        bytes decoded leniently. Banks are inconsistent about encoding, so
        undecodable bytes are dropped rather than raising.
        """
        if self.extension == "pdf" or self.content[:5] == b"%PDF-":
            from apps.parsers.utils.pdf import extract_text

            return extract_text(self)
        for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
            try:
                return self.content.decode(encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return self.content.decode("utf-8", errors="ignore")

    @cached_property
    def head(self) -> str:
        """First 4 KB of text — enough for `can_parse` to find a bank name."""
        return self.text[:4096]

    def contains_any(self, *needles: str) -> bool:
        """Case-insensitive search over the whole text."""
        haystack = self.text.lower()
        return any(needle.lower() in haystack for needle in needles)


class BaseParser(ABC):
    """Subclass this to support a bank.

    Put the subclass in `apps/parsers/banks/<bank>/parser.py`; the registry
    discovers it automatically, so there is no list to add yourself to and no
    merge conflict with anyone adding a different bank.
    """

    bank_slug: str
    """Stable machine name, e.g. "hdfc". Must match the directory name."""

    display_name: str
    """Shown to users, e.g. "HDFC Bank — Savings"."""

    statement_kind: StatementKind
    file_formats: list[str]
    """Extensions handled, e.g. ["pdf", "csv"]. Used to skip parsers early."""

    @classmethod
    @abstractmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        """How confident are you that this file is yours?

        Keep it cheap — look for a bank name, an IFSC prefix, a distinctive
        header. This runs for every registered parser on every upload.
        """

    @abstractmethod
    def parse(self, file: ParsedFile) -> ParsedStatement:
        """Extract transactions. Raise ParseError with a message a user can act on."""

    # -- helpers for subclasses ------------------------------------------

    @classmethod
    def handles_extension(cls, file: ParsedFile) -> bool:
        return file.extension in cls.file_formats

    def build_statement(
        self, transactions: list[ParsedTransaction], **kwargs: Any
    ) -> ParsedStatement:
        """Wrap transactions in a ParsedStatement, tagging it with this parser."""
        return ParsedStatement(
            transactions=transactions,
            bank_slug=self.bank_slug,
            statement_kind=self.statement_kind,
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.bank_slug}/{self.statement_kind}>"
