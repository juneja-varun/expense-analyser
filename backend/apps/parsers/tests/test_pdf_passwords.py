"""Password handling for encrypted statement PDFs.

Most Indian card issuers email password-protected statements, so this path is
load-bearing — and it was silently broken: pdfplumber re-raises pdfminer's
`PDFPasswordIncorrect` wrapped in its own `PdfminerException`, so catching the
former by type never fired. An encrypted statement was reported as "no text
layer", which reads as "your PDF is a scan" and sends the user to re-download a
file that was never the problem.

These tests drive the wrapper directly rather than through a fixture: an
encrypted PDF committed to the repo would be a fixture nobody could regenerate,
and the defect was entirely in how the exception was unwrapped.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from apps.parsers.base import ParsedFile, ParseError
from apps.parsers.utils.pdf import (
    PasswordRequired,
    _is_password_error,
    is_encrypted,
    open_pdf,
)


def wrapped() -> PdfminerException:
    """How pdfplumber actually surfaces a wrong password."""
    return PdfminerException(PDFPasswordIncorrect())


def chained() -> PdfminerException:
    """The same thing raised with `from`, which sets __cause__ instead."""
    try:
        try:
            raise PDFPasswordIncorrect
        except PDFPasswordIncorrect as exc:
            raise PdfminerException("wrapped") from exc
    except PdfminerException as exc:
        return exc


class TestRecognisingAPasswordError:
    def test_sees_through_pdfplumbers_wrapper(self) -> None:
        """The regression. `except PDFPasswordIncorrect` alone never matches this."""
        assert _is_password_error(wrapped()) is True

    def test_sees_through_an_exception_chain(self) -> None:
        assert _is_password_error(chained()) is True

    def test_still_recognises_the_bare_error(self) -> None:
        assert _is_password_error(PDFPasswordIncorrect()) is True

    def test_does_not_claim_every_failure_is_a_password(self) -> None:
        """A corrupt file must not be reported as needing a password."""
        assert _is_password_error(PdfminerException("not a PDF at all")) is False
        assert _is_password_error(ValueError("something else")) is False


class TestIsEncrypted:
    def test_true_when_the_password_error_is_wrapped(self, tmp_path, monkeypatch) -> None:
        file = ParsedFile(path=tmp_path / "statement.pdf", filename="statement.pdf")

        def refuse(*args, **kwargs):
            raise wrapped()

        monkeypatch.setattr(pdfplumber, "open", refuse)

        assert is_encrypted(file) is True

    def test_false_for_a_file_that_is_merely_broken(self, tmp_path, monkeypatch) -> None:
        file = ParsedFile(path=tmp_path / "statement.pdf", filename="statement.pdf")

        def refuse(*args, **kwargs):
            raise PdfminerException("truncated")

        monkeypatch.setattr(pdfplumber, "open", refuse)

        assert is_encrypted(file) is False


class TestOpeningAnEncryptedPdf:
    def test_asks_for_a_password_rather_than_blaming_the_file(self, tmp_path, monkeypatch) -> None:
        file = ParsedFile(path=tmp_path / "statement.pdf", filename="statement.pdf")
        monkeypatch.setattr(pdfplumber, "open", lambda *a, **k: (_ for _ in ()).throw(wrapped()))

        with pytest.raises(PasswordRequired, match="password-protected"):
            open_pdf(file)

    def test_tries_the_supplied_password_first(self, tmp_path, monkeypatch) -> None:
        """A password that works must not be beaten to it by the empty one."""
        file = ParsedFile(
            path=tmp_path / "statement.pdf", filename="statement.pdf", password="s3cret"
        )
        tried: list[str] = []

        def record(path, password="", **kwargs):
            tried.append(password)
            if password != "s3cret":
                raise wrapped()
            return "opened"

        monkeypatch.setattr(pdfplumber, "open", record)

        assert open_pdf(file) == "opened"
        assert tried == ["s3cret"]

    def test_a_corrupt_file_is_not_reported_as_a_password_problem(
        self, tmp_path, monkeypatch
    ) -> None:
        file = ParsedFile(path=tmp_path / "statement.pdf", filename="statement.pdf")

        def refuse(*args, **kwargs):
            raise PdfminerException("truncated")

        monkeypatch.setattr(pdfplumber, "open", refuse)

        with pytest.raises(ParseError) as caught:
            open_pdf(file)
        assert not isinstance(caught.value, PasswordRequired)


class TestRealStatements:
    """Guards the exact shape that broke, if a sample happens to be present.

    Skipped everywhere by default — the file is a real statement and never
    enters the repository. See docs/anonymising-statements.md.
    """

    def test_an_encrypted_statement_is_recognised(self) -> None:
        sample = Path(__file__).resolve().parents[3] / "statements" / "encrypted.pdf"
        if not sample.exists():
            pytest.skip("no local encrypted sample")
        assert is_encrypted(ParsedFile(path=sample, filename=sample.name)) is True
