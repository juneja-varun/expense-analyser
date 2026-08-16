from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from apps.accounts.models import User
from apps.sources.models import Source
from apps.statements.models import Statement
from apps.statements.services import import_statement
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parents[2] / "parsers" / "banks"
HDFC_FIXTURE = FIXTURES / "hdfc" / "tests" / "fixtures" / "hdfc_savings_2024_04.xls"
ICICI_FIXTURE = FIXTURES / "icici" / "tests" / "fixtures" / "icici_credit_card_2024_04.pdf"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def household():
    return User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household


def upload(household, fixture: Path) -> Statement:
    statement = Statement(household=household, original_filename=fixture.name)
    statement.file.save(fixture.name, ContentFile(fixture.read_bytes()), save=False)
    statement.save()
    return statement


class TestSuccessfulImport:
    def test_creates_transactions_from_a_bank_statement(self, household) -> None:
        result = import_statement(upload(household, HDFC_FIXTURE))

        assert result.statement.status == Statement.Status.PARSED
        assert result.created == 10
        assert result.duplicates == 0
        assert Transaction.objects.for_household(household).count() == 10

    def test_records_the_statement_period_and_source(self, household) -> None:
        statement = import_statement(upload(household, HDFC_FIXTURE)).statement

        assert statement.bank_slug == "hdfc"
        assert statement.statement_kind == "bank"
        assert str(statement.period_start) == "2024-04-01"
        assert str(statement.period_end) == "2024-04-28"
        assert statement.source.account_hint == "XXXXXXXX1234"

    def test_preserves_signs_and_the_raw_description(self, household) -> None:
        import_statement(upload(household, HDFC_FIXTURE))

        salary = Transaction.objects.for_household(household).get(
            description__startswith="SALARY CREDIT"
        )
        swiggy = Transaction.objects.for_household(household).get(description__contains="SWIGGY")

        assert salary.amount == Decimal("125000.00")
        assert swiggy.amount == Decimal("-450.00")
        assert swiggy.description == "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT"
        assert swiggy.is_debit

    def test_card_statement_imports_with_normalised_signs(self, household) -> None:
        result = import_statement(upload(household, ICICI_FIXTURE))

        assert result.created == 10
        assert result.statement.source.kind == Source.Kind.CREDIT_CARD

        purchase = Transaction.objects.for_household(household).get(description__contains="SWIGGY")
        refund = Transaction.objects.for_household(household).get(description__startswith="REFUND")

        assert purchase.amount < 0
        assert refund.amount > 0


class TestDeduplication:
    def test_reuploading_the_same_file_adds_nothing(self, household) -> None:
        """Users routinely download overlapping ranges — a second upload must
        not double their spending."""
        import_statement(upload(household, HDFC_FIXTURE))
        second = import_statement(upload(household, HDFC_FIXTURE))

        assert second.created == 0
        assert second.duplicates == 10
        assert second.was_entirely_duplicate
        assert Transaction.objects.for_household(household).count() == 10

    def test_the_statement_reports_it_was_entirely_duplicate(self, household) -> None:
        """An upload that adds nothing otherwise looks like a silent failure."""
        import_statement(upload(household, HDFC_FIXTURE))
        statement = import_statement(upload(household, HDFC_FIXTURE)).statement

        assert statement.status == Statement.Status.PARSED
        assert statement.was_entirely_duplicate

    def test_the_same_file_in_two_households_stays_separate(self, household) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household

        import_statement(upload(household, HDFC_FIXTURE))
        result = import_statement(upload(other, HDFC_FIXTURE))

        assert result.created == 10
        assert Transaction.objects.for_household(household).count() == 10
        assert Transaction.objects.for_household(other).count() == 10

    def test_bank_and_card_statements_do_not_collide(self, household) -> None:
        import_statement(upload(household, HDFC_FIXTURE))
        result = import_statement(upload(household, ICICI_FIXTURE))

        assert result.duplicates == 0
        assert Transaction.objects.for_household(household).count() == 20


class TestFailedImport:
    def test_unrecognised_file_is_recorded_not_raised(self, household, tmp_path) -> None:
        junk = tmp_path / "holiday-photo.csv"
        junk.write_text("this is not a bank statement\n")

        result = import_statement(upload(household, junk))

        assert result.statement.status == Statement.Status.FAILED
        assert result.created == 0
        assert Transaction.objects.for_household(household).count() == 0

    def test_failure_message_tells_the_user_what_to_do(self, household, tmp_path) -> None:
        junk = tmp_path / "holiday-photo.csv"
        junk.write_text("this is not a bank statement\n")

        message = import_statement(upload(household, junk)).statement.error_message

        assert "no parser recognised" in message.lower()
        assert "adding-a-bank-parser" in message

    def test_a_failed_import_leaves_no_partial_data(self, household, monkeypatch) -> None:
        """Persistence is atomic: a half-imported statement would be worse than
        none, because dedupe would then skip the missing rows on retry."""
        monkeypatch.setattr(
            "apps.statements.services.resolve_source",
            lambda household, parsed: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError):
            import_statement(upload(household, HDFC_FIXTURE))

        assert Transaction.objects.for_household(household).count() == 0


class TestProvenance:
    def test_transactions_link_back_to_their_upload(self, household) -> None:
        statement = import_statement(upload(household, HDFC_FIXTURE)).statement

        assert statement.transactions.count() == 10

    def test_deleting_a_statement_keeps_its_transactions(self, household) -> None:
        """Removing an upload record must not delete a user's financial history."""
        statement = import_statement(upload(household, HDFC_FIXTURE)).statement
        statement.delete()

        assert Transaction.objects.for_household(household).count() == 10

    def test_upload_path_does_not_leak_the_original_filename(self, household) -> None:
        """Uploaded filenames often contain an account number."""
        statement = upload(household, HDFC_FIXTURE)

        assert "hdfc_savings" not in statement.file.name
        assert str(household.pk) in statement.file.name
        assert statement.original_filename == HDFC_FIXTURE.name


@pytest.fixture(autouse=True)
def _cleanup_media(media_root):
    yield
    shutil.rmtree(media_root, ignore_errors=True)
