"""Categorisation as it happens during a real statement import."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from apps.accounts.models import User
from apps.categories.models import Category
from apps.rules.engine import learn_from_recategorisation
from apps.rules.models import CategoryRule
from apps.statements.models import Statement
from apps.statements.services import import_statement
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "parsers"
    / "banks"
    / "hdfc"
    / "tests"
    / "fixtures"
    / "hdfc_savings_2024_04.xls"
)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def household():
    """A household with the category tree but no rules.

    The bundled merchant rules would categorise these fixtures for us, which is
    the subject of test_builtin_rules.py. Here we want to observe the engine
    acting on rules the test itself created.
    """
    created = User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household
    CategoryRule.objects.for_household(created).delete()
    return created


def upload(household) -> Statement:
    statement = Statement(household=household, original_filename=FIXTURE.name)
    statement.file.save(FIXTURE.name, ContentFile(FIXTURE.read_bytes()), save=False)
    statement.save()
    return statement


def category(household, name: str) -> Category:
    return Category.objects.for_household(household).get(name=name)


class TestCategorisationDuringImport:
    def test_rules_are_applied_as_the_statement_imports(self, household) -> None:
        """A statement should never appear as a wall of uncategorised rows."""
        CategoryRule.objects.create(
            household=household,
            category=category(household, "Food Delivery"),
            pattern="SWIGGY",
        )

        import_statement(upload(household))

        swiggy = Transaction.objects.for_household(household).get(description__contains="SWIGGY")
        assert swiggy.category.name == "Food Delivery"

    def test_transactions_without_a_matching_rule_stay_uncategorised(self, household) -> None:
        import_statement(upload(household))

        uncategorised = Transaction.objects.for_household(household).filter(category__isnull=True)
        assert uncategorised.exists()

    def test_import_succeeds_with_no_rules_at_all(self, household) -> None:
        result = import_statement(upload(household))

        assert result.created == 10
        assert Transaction.objects.for_household(household).count() == 10


class TestLearningAcrossImports:
    def test_correcting_a_merchant_fixes_the_next_statement(self, household) -> None:
        """The core promise of the rules engine: correct a merchant once and
        every future statement files it correctly, with no AI involved."""
        import_statement(upload(household))

        swiggy = Transaction.objects.for_household(household).get(description__contains="SWIGGY")
        assert swiggy.category is None

        food_delivery = category(household, "Food Delivery")
        learn_from_recategorisation(swiggy, food_delivery)
        swiggy.category = food_delivery
        swiggy.is_categorised_by_user = True
        swiggy.save()

        # A later statement containing the same merchant, differently worded.
        second = Statement(household=household, original_filename="may.xls")
        second.file.save(
            "may.xls",
            ContentFile(
                b"HDFC BANK LTD\n"
                b"Account No : XXXXXXXX1234\n\n"
                b"Date\tNarration\tChq./Ref.No.\tValue Dt\t"
                b"Withdrawal Amt.\tDeposit Amt.\tClosing Balance\n"
                b"05/05/24\tUPI/SWIGGY LIMITED/swiggy@examplebank/ORDER 77\t"
                b"409400000001\t05/05/24\t612.00\t0.00\t89,476.25\n"
            ),
            save=False,
        )
        second.save()
        import_statement(second)

        may_order = Transaction.objects.for_household(household).get(txn_date__month=5)
        assert may_order.category == food_delivery

    def test_the_earlier_manual_choice_is_never_overwritten(self, household) -> None:
        import_statement(upload(household))

        swiggy = Transaction.objects.for_household(household).get(description__contains="SWIGGY")
        groceries = category(household, "Groceries")
        swiggy.category = groceries
        swiggy.is_categorised_by_user = True
        swiggy.save()

        # A rule that would say otherwise, plus a re-import.
        CategoryRule.objects.create(
            household=household,
            category=category(household, "Food Delivery"),
            pattern="SWIGGY",
        )
        import_statement(upload(household))

        swiggy.refresh_from_db()
        assert swiggy.category == groceries
