from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.parsers.base import ParsedStatement
from apps.sources.models import Source
from apps.sources.services import resolve_source

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    return User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household


def statement(**kwargs) -> ParsedStatement:
    defaults = {
        "transactions": [],
        "bank_slug": "hdfc",
        "statement_kind": "bank",
        "source_hint": "XXXXXXXX1234",
    }
    return ParsedStatement(**{**defaults, **kwargs})


class TestMatchingByAccountHint:
    def test_creates_a_source_on_first_upload(self, household) -> None:
        source = resolve_source(household, statement())

        assert source.bank_slug == "hdfc"
        assert source.account_hint == "XXXXXXXX1234"
        assert source.kind == Source.Kind.BANK
        assert source.name == "HDFC Account"

    def test_second_upload_reuses_the_same_source(self, household) -> None:
        """The point of the hint: uploading next month's statement must not
        create a second account."""
        first = resolve_source(household, statement())
        second = resolve_source(household, statement())

        assert first.pk == second.pk
        assert Source.objects.for_household(household).count() == 1

    def test_different_accounts_at_the_same_bank_stay_separate(self, household) -> None:
        salary = resolve_source(household, statement(source_hint="XXXXXXXX1234"))
        savings = resolve_source(household, statement(source_hint="XXXXXXXX9999"))

        assert salary.pk != savings.pk
        assert Source.objects.for_household(household).count() == 2

    def test_reuse_survives_the_user_renaming_the_source(self, household) -> None:
        source = resolve_source(household, statement())
        source.name = "My salary account"
        source.save()

        assert resolve_source(household, statement()).pk == source.pk
        assert Source.objects.for_household(household).get().name == "My salary account"


class TestCreditCards:
    def test_card_statement_creates_a_credit_card_source(self, household) -> None:
        source = resolve_source(
            household,
            statement(bank_slug="icici", statement_kind="credit_card", source_hint="XXXX4321"),
        )

        assert source.kind == Source.Kind.CREDIT_CARD
        assert source.name == "ICICI Credit Card"
        assert source.is_credit_card

    def test_card_and_account_at_one_bank_are_separate_sources(self, household) -> None:
        account = resolve_source(household, statement(source_hint="XXXXXXXX1234"))
        card = resolve_source(
            household,
            statement(statement_kind="credit_card", source_hint="XXXX4321"),
        )

        assert account.pk != card.pk


class TestWithoutAnAccountHint:
    def test_falls_back_to_the_existing_source_for_that_bank(self, household) -> None:
        """Some statements print no account number. Creating a fresh source on
        every upload would be worse than reusing the obvious one."""
        first = resolve_source(household, statement(source_hint=None))
        second = resolve_source(household, statement(source_hint=None))

        assert first.pk == second.pk
        assert Source.objects.for_household(household).count() == 1

    def test_ignores_archived_sources_when_falling_back(self, household) -> None:
        old = resolve_source(household, statement(source_hint=None))
        old.is_archived = True
        old.save()

        new = resolve_source(household, statement(source_hint=None))

        assert new.pk != old.pk

    def test_a_later_hinted_upload_creates_its_own_source(self, household) -> None:
        """We cannot retrofit a hint onto the unhinted source without risking
        attaching it to the wrong account, so a new one is correct here."""
        unhinted = resolve_source(household, statement(source_hint=None))
        hinted = resolve_source(household, statement(source_hint="XXXXXXXX1234"))

        assert unhinted.pk != hinted.pk


class TestHouseholdIsolation:
    def test_sources_are_never_shared_between_households(self, household) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household

        mine = resolve_source(household, statement())
        theirs = resolve_source(other, statement())

        assert mine.pk != theirs.pk
        assert list(Source.objects.for_household(household)) == [mine]
