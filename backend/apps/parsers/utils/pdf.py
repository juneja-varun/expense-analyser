"""PDF text and table extraction, including encrypted statements.

Most Indian card issuers email password-protected PDFs. The password is usually
derived from the cardholder's details — date of birth, name fragments, last
four digits — in a per-issuer pattern, so `candidate_passwords` builds the
common shapes from what the user tells us rather than asking them to work out
which variant their bank uses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

from apps.parsers.base import ParseError

if TYPE_CHECKING:
    from datetime import date

    from apps.parsers.base import ParsedFile

logger = logging.getLogger(__name__)

__all__ = [
    "PasswordRequired",
    "candidate_passwords",
    "extract_tables",
    "extract_text",
    "is_encrypted",
    "open_pdf",
]


class PasswordRequired(ParseError):
    """The PDF is encrypted and no working password was supplied."""

    def __init__(self, message: str = "") -> None:
        super().__init__(
            message
            or "This statement is password-protected. Enter the password your bank "
            "uses — usually your date of birth, or a mix of your name and card digits."
        )


def is_encrypted(file: ParsedFile) -> bool:
    try:
        with pdfplumber.open(file.path):
            return False
    except PDFPasswordIncorrect:
        return True
    except Exception:
        return False


def open_pdf(file: ParsedFile) -> pdfplumber.PDF:
    """Open a PDF, trying the supplied password if there is one.

    Caller is responsible for closing, or use it as a context manager.
    """
    passwords: list[str] = [""]
    if file.password:
        passwords.insert(0, file.password)

    last_error: Exception | None = None
    for password in passwords:
        try:
            return pdfplumber.open(file.path, password=password)
        except PDFPasswordIncorrect as exc:
            last_error = exc
            continue
        except Exception as exc:
            raise ParseError(f"Could not read the PDF: {exc}") from exc

    raise PasswordRequired() from last_error


def extract_text(file: ParsedFile) -> str:
    """All text in the document, pages joined by newlines.

    Returns an empty string for a scanned PDF with no text layer — parsers
    should treat "no text" as "not mine" rather than crashing, so that a scan
    produces a clear "we can't read this" instead of a traceback.
    """
    try:
        with open_pdf(file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except PasswordRequired:
        raise
    except ParseError:
        return ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("PDF text extraction failed for %s: %s", file.filename, exc)
        return ""


def extract_tables(file: ParsedFile, **settings: Any) -> list[list[list[str | None]]]:
    """Every table in the document, as a list of row-lists per table.

    `settings` is passed through to pdfplumber's `extract_tables`. Statements
    without ruling lines usually need a text-based strategy:

        extract_tables(file, vertical_strategy="text", horizontal_strategy="text")
    """
    tables: list[list[list[str | None]]] = []
    with open_pdf(file) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables(settings or None) or []:
                if table:
                    tables.append(table)
    return tables


def candidate_passwords(
    *,
    date_of_birth: date | None = None,
    name: str | None = None,
    last_four: str | None = None,
) -> list[str]:
    """Common Indian statement password patterns, most likely first.

    Issuers rarely document their scheme, and users generally know their own
    details but not which combination their bank wants — so try the shapes
    rather than making them guess.
    """
    candidates: list[str] = []

    if date_of_birth is not None:
        candidates += [
            date_of_birth.strftime("%d%m%Y"),  # 01011990 — the most common
            date_of_birth.strftime("%d%m%y"),
            date_of_birth.strftime("%d-%m-%Y"),
            date_of_birth.strftime("%Y%m%d"),
            date_of_birth.strftime("%d%b%Y").upper(),
        ]

    if name:
        first = name.strip().split()[0] if name.strip() else ""
        if first:
            candidates += [first.upper(), first.lower(), first[:4].upper(), first[:5].lower()]

            # Several issuers concatenate a name fragment with DOB or card digits.
            if date_of_birth is not None:
                candidates += [
                    f"{first[:4].upper()}{date_of_birth.strftime('%d%m')}",
                    f"{first[:4].lower()}{date_of_birth.strftime('%d%m%Y')}",
                ]
            if last_four:
                candidates += [
                    f"{first[:4].upper()}{last_four}",
                    f"{first[:4].lower()}{last_four}",
                ]

    if last_four:
        candidates.append(last_four)
        if date_of_birth is not None:
            candidates.append(f"{last_four}{date_of_birth.strftime('%d%m')}")

    seen: set[str] = set()
    return [c for c in candidates if c and not (c in seen or seen.add(c))]
