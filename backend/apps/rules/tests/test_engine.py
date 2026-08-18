from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.categories.models import Category
from apps.rules.engine import (
    categorise,
    categorise_transactions,
    distinctive_fragment,
    learn_from_recategorisation,
)
from apps.rules.models import CategoryRule, extract_vpa, matchable_text
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    """A household with the category tree but no rules.

    Registration also seeds the bundled merchant rules (see
    test_builtin_rules.py). These tests are about engine mechanics, so they
    start from an empty rule set to keep the precedence under test explicit.
    """
    created = User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household
    CategoryRule.objects.for_household(created).delete()
    return created


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="HDFC", kind=Source.Kind.BANK)


@pytest.fixture
def food(household):
    return Category.objects.for_household(household).get(name="Food Delivery")


@pytest.fixture
def groceries(household):
    return Category.objects.for_household(household).get(name="Groceries")


def make_transaction(household, source, description: str, amount: str = "-450.00") -> Transaction:
    return Transaction.objects.create(
        household=household,
        source=source,
        txn_date=date(2024, 4, 3),
        description=description,
        amount=Decimal(amount),
    )


class TestMatchTypes:
    @pytest.mark.parametrize(
        ("match_type", "pattern", "description", "expected"),
        [
            (CategoryRule.MatchType.CONTAINS, "swiggy", "UPI-SWIGGY-PAYMENT", True),
            (CategoryRule.MatchType.CONTAINS, "zomato", "UPI-SWIGGY-PAYMENT", False),
            (CategoryRule.MatchType.EXACT, "UPI-SWIGGY", "UPI-SWIGGY", True),
            (CategoryRule.MatchType.EXACT, "SWIGGY", "UPI-SWIGGY", False),
            (CategoryRule.MatchType.STARTS_WITH, "UPI", "UPI-SWIGGY", True),
            (CategoryRule.MatchType.STARTS_WITH, "SWIGGY", "UPI-SWIGGY", False),
            (CategoryRule.MatchType.REGEX, r"SWIGGY|ZOMATO", "UPI-ZOMATO-PAY", True),
            (CategoryRule.MatchType.REGEX, r"^ATM", "UPI-ZOMATO-PAY", False),
        ],
    )
    def test_matching(self, household, food, match_type, pattern, description, expected) -> None:
        rule = CategoryRule(
            household=household, category=food, match_type=match_type, pattern=pattern
        )
        assert rule.matches(description) is expected

    def test_matching_is_case_and_whitespace_insensitive(self, household, food) -> None:
        rule = CategoryRule(household=household, category=food, pattern="swiggy")
        assert rule.matches("upi-Swiggy-payment")
        assert rule.matches("UPI   SWIGGY    PAYMENT")

    def test_inactive_rules_never_match(self, household, food) -> None:
        rule = CategoryRule(household=household, category=food, pattern="SWIGGY", is_active=False)
        assert rule.matches("UPI-SWIGGY") is False

    def test_a_broken_regex_does_not_break_matching(self, household, food) -> None:
        """One malformed rule must not stop the rest from categorising."""
        rule = CategoryRule(
            household=household,
            category=food,
            match_type=CategoryRule.MatchType.REGEX,
            pattern="SWIGGY",
        )
        rule.pattern = "([unclosed"  # bypass validation, as a direct DB edit would
        assert rule.matches("UPI-SWIGGY") is False


class TestUpiVpaMatching:
    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT", "swiggy@examplebank"),
            ("UPI-ASHA S-asha.sharma@okexamplebank-SPLIT", "asha.sharma@okexamplebank"),
            ("NEFT DR-BANK0000000-RAHUL K-RENT", None),
            ("POS 000000000000 IRCTC ONLINE", None),
        ],
    )
    def test_extraction(self, description, expected) -> None:
        assert extract_vpa(description) == expected

    def test_vpa_rule_matches_regardless_of_surrounding_text(self, household, food) -> None:
        """The VPA is the only stable part of a UPI narration — the payee name
        and note differ between banks for the same merchant."""
        rule = CategoryRule(
            household=household,
            category=food,
            match_type=CategoryRule.MatchType.UPI_VPA,
            pattern="swiggy@examplebank",
        )

        assert rule.matches("UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT")
        assert rule.matches("UPI/SWIGGY LIMITED/swiggy@examplebank/ORDER 12345")
        assert not rule.matches("UPI-ZOMATO-ZOMATO@EXAMPLEBANK-PAYMENT")


class TestPrecedence:
    def test_user_rules_beat_learned_and_builtin(self, household, food, groceries) -> None:
        builtin = CategoryRule.objects.create(
            household=household,
            category=groceries,
            pattern="SWIGGY",
            origin=CategoryRule.Origin.BUILTIN,
        )
        user = CategoryRule.objects.create(
            household=household,
            category=food,
            pattern="SWIGGY ",
            match_type=CategoryRule.MatchType.STARTS_WITH,
            origin=CategoryRule.Origin.USER,
        )

        rules = sorted([builtin, user], key=lambda r: (-r.priority, r.pk))
        assert categorise("SWIGGY ORDER", rules) == user

    def test_learned_beats_builtin(self, household, food, groceries) -> None:
        builtin = CategoryRule.objects.create(
            household=household,
            category=groceries,
            pattern="SWIGGY",
            origin=CategoryRule.Origin.BUILTIN,
        )
        learned = CategoryRule.objects.create(
            household=household,
            category=food,
            pattern="SWIGGY",
            match_type=CategoryRule.MatchType.STARTS_WITH,
            origin=CategoryRule.Origin.LEARNED,
        )

        rules = sorted([builtin, learned], key=lambda r: (-r.priority, r.pk))
        assert categorise("SWIGGY ORDER", rules) == learned

    def test_explicit_priority_overrides_the_origin_default(self, household, food) -> None:
        rule = CategoryRule.objects.create(
            household=household,
            category=food,
            pattern="SWIGGY",
            origin=CategoryRule.Origin.BUILTIN,
            priority=999,
        )
        assert rule.priority == 999


class TestCategoriseTransactions:
    def test_applies_rules_to_uncategorised_transactions(self, household, source, food) -> None:
        CategoryRule.objects.create(household=household, category=food, pattern="SWIGGY")
        txn = make_transaction(household, source, "UPI-SWIGGY-PAYMENT")

        result = categorise_transactions(household)

        txn.refresh_from_db()
        assert txn.category == food
        assert result.categorised == 1
        assert result.unmatched == 0

    def test_leaves_unmatched_transactions_uncategorised(self, household, source) -> None:
        make_transaction(household, source, "SOME UNKNOWN MERCHANT")

        result = categorise_transactions(household)

        assert result.categorised == 0
        assert result.unmatched == 1

    def test_never_overrides_a_manual_categorisation(
        self, household, source, food, groceries
    ) -> None:
        """The rule that keeps the app trustworthy: re-running categorisation
        on every import must not undo a deliberate choice."""
        txn = make_transaction(household, source, "UPI-SWIGGY-PAYMENT")
        txn.category = groceries
        txn.is_categorised_by_user = True
        txn.save()
        CategoryRule.objects.create(household=household, category=food, pattern="SWIGGY")

        result = categorise_transactions(household)

        txn.refresh_from_db()
        assert txn.category == groceries
        assert result.skipped_user_categorised == 1

    def test_can_be_forced_to_include_user_categorised(
        self, household, source, food, groceries
    ) -> None:
        """Only for an explicit "re-run everything" the user asked for."""
        txn = make_transaction(household, source, "UPI-SWIGGY-PAYMENT")
        txn.category = groceries
        txn.is_categorised_by_user = True
        txn.save()
        CategoryRule.objects.create(household=household, category=food, pattern="SWIGGY")

        categorise_transactions(household, include_user_categorised=True)

        txn.refresh_from_db()
        assert txn.category == food

    def test_records_how_often_each_rule_fires(self, household, source, food) -> None:
        """Surfaces dead rules the user can clean up."""
        rule = CategoryRule.objects.create(household=household, category=food, pattern="SWIGGY")
        make_transaction(household, source, "UPI-SWIGGY-ONE")
        make_transaction(household, source, "UPI-SWIGGY-TWO", amount="-120.00")

        categorise_transactions(household)

        rule.refresh_from_db()
        assert rule.match_count == 2

    def test_no_rules_is_not_an_error(self, household, source) -> None:
        make_transaction(household, source, "UPI-SWIGGY-PAYMENT")

        result = categorise_transactions(household)

        assert result.categorised == 0
        assert result.unmatched == 1

    def test_rules_never_cross_households(self, household, source, food) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        # Their bundled rules would categorise this correctly for their own
        # reasons; clearing them leaves my rule as the only one in existence,
        # so the assertion can only pass if scoping holds.
        CategoryRule.objects.for_household(other).delete()
        other_source = Source.objects.create(household=other, name="HDFC", kind=Source.Kind.BANK)
        CategoryRule.objects.create(household=household, category=food, pattern="SWIGGY")
        their_txn = make_transaction(other, other_source, "UPI-SWIGGY-PAYMENT")

        categorise_transactions(other)

        their_txn.refresh_from_db()
        assert their_txn.category is None


class TestLearning:
    def test_recategorising_creates_a_vpa_rule(self, household, source, food) -> None:
        txn = make_transaction(household, source, "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT")

        rule = learn_from_recategorisation(txn, food)

        assert rule is not None
        assert rule.match_type == CategoryRule.MatchType.UPI_VPA
        assert rule.pattern == "swiggy@examplebank"
        assert rule.origin == CategoryRule.Origin.LEARNED

    def test_the_learned_rule_categorises_future_transactions(
        self, household, source, food
    ) -> None:
        """Correct a merchant once; every future statement files it correctly."""
        first = make_transaction(household, source, "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-ORDER1")
        learn_from_recategorisation(first, food)

        later = make_transaction(
            household, source, "UPI/SWIGGY LTD/swiggy@examplebank/ORDER 999", amount="-812.00"
        )
        categorise_transactions(household)

        later.refresh_from_db()
        assert later.category == food

    def test_falls_back_to_a_distinctive_word_without_a_vpa(
        self, household, source, groceries
    ) -> None:
        txn = make_transaction(household, source, "POS 000000000000 BIGBASKET ONLINE")

        rule = learn_from_recategorisation(txn, groceries)

        assert rule is not None
        assert rule.match_type == CategoryRule.MatchType.CONTAINS
        assert rule.pattern == "BIGBASKET"

    def test_changing_your_mind_updates_the_existing_rule(
        self, household, source, food, groceries
    ) -> None:
        txn = make_transaction(household, source, "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAY")
        learn_from_recategorisation(txn, food)

        rule = learn_from_recategorisation(txn, groceries)

        assert rule.category == groceries
        assert CategoryRule.objects.for_household(household).count() == 1

    def test_learns_nothing_when_there_is_nothing_reliable(self, household, source, food) -> None:
        """A bad rule that mis-files future transactions is worse than none."""
        txn = make_transaction(household, source, "NEFT DR 123456")

        assert learn_from_recategorisation(txn, food) is None

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("UPI-SWIGGY-PAYMENT", "SWIGGY"),
            ("POS 000000000000 IRCTC ONLINE", "IRCTC"),
            ("ACH D- HDFC LIFE INSURANCE", "INSURANCE"),
            ("NEFT DR 123456", None),
            ("UPI TO REF TXN", None),
        ],
    )
    def test_distinctive_fragment(self, description, expected) -> None:
        assert distinctive_fragment(description) == expected

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            # The payee leads and the rail trails, so the longest word is the
            # wrong pick. Each of these came from a real ICICI statement.
            ("CHAI HAI NA UPI/CHAI HAI N/paytm.d1088744/UPI/AXIS", "CHAI"),
            ("THE JUICY SCOOP UPI/THE JUICY/q121481771@ybl/UPI/YES BANK", "JUICY"),
            ("CMS TRANSACTION CMS/ CMS5739637210/ACUVER CONS", "ACUVER"),
        ],
    )
    def test_learns_the_payee_not_the_payment_rail(self, description, expected) -> None:
        """Regression: these used to learn PAYTM, JUICY and TRANSACTION.

        A rule learned from the rail is actively harmful — one tea shop paid via
        Paytm would recategorise every future Paytm transaction, and
        `CONTAINS "TRANSACTION"` matches most narrations ever written.
        """
        assert distinctive_fragment(description) == expected


class TestRoutingDetailsDoNotDecideCategories:
    """ICICI narrations end with the bank that moved the money.

    Those tails are full of bank and wallet names, which is exactly what
    merchant patterns look for. Matching against them is silent and wrong: the
    amount is right, so nothing looks broken until a budget is inexplicably
    over. Found by importing two real months of statements.
    """

    def test_a_person_paid_via_a_payments_bank_is_not_an_internet_bill(
        self, household, food
    ) -> None:
        rule = CategoryRule.objects.create(household=household, category=food, pattern="AIRTEL")
        routed_through_airtel = (
            "jishanmalik15233 okicici UPI/jishanmali/jishanmalik152/UPI/"
            "AIRTEL PAY/618593247610/ICI9d89890ddf364735b532b7d8c3a39d3f/"
        )

        assert rule.matches(routed_through_airtel) is False

    def test_but_the_real_merchant_still_matches(self, household, food) -> None:
        rule = CategoryRule.objects.create(household=household, category=food, pattern="AIRTEL")
        actual_airtel_bill = (
            "Airtel UPI/Airtel/airtel4.payu@i/Upi Mandat/ICICI Bank/618519453610/ICIabc123/"
        )

        assert rule.matches(actual_airtel_bill) is True

    def test_the_vpa_survives_stripping(self, household) -> None:
        """The VPA sits before the tail, and is the most reliable identifier."""
        narration = "Netflix UPI/Netflix/netflix.bd@axi/MandateExe/AXIS BANK/123456789012/ICIx/"

        assert extract_vpa(narration) == "netflix.bd@axi"

    def test_a_narration_without_a_tail_is_left_alone(self) -> None:
        plain = "CMS TRANSACTION CMS/ CMS5794598716/ACUVER CONSULTING PVT LTD"

        assert matchable_text(plain) == plain

    def test_the_stored_description_is_never_modified(self, household, source, food) -> None:
        """Users recognise their transactions by the full narration."""
        narration = "Airtel UPI/Airtel/airtel4.payu@i/Upi Mandat/ICICI Bank/618519453610/ICIabc/"
        txn = make_transaction(household, source, narration)

        CategoryRule.objects.create(household=household, category=food, pattern="AIRTEL")
        categorise_transactions(household)

        txn.refresh_from_db()
        assert txn.description == narration


class TestFixingARuleUndoesItsDamage:
    """Otherwise correcting a bad rule silently changes nothing.

    A category assigned by a rule is only as good as that rule. When the rule
    stops claiming a transaction, the category it left behind is stale state,
    and it would go on feeding a budget that nobody can explain.
    """

    def test_a_category_is_cleared_when_no_rule_claims_it(self, household, source, food) -> None:
        txn = make_transaction(household, source, "AIRTEL PAYMENTS")
        rule = CategoryRule.objects.create(household=household, category=food, pattern="AIRTEL")
        categorise_transactions(household)
        txn.refresh_from_db()
        assert txn.category_id == food.pk

        rule.delete()
        result = categorise_transactions(household)

        txn.refresh_from_db()
        assert txn.category_id is None
        assert result.cleared == 1

    def test_but_a_choice_the_user_made_survives(self, household, source, food) -> None:
        """Clearing applies to what rules assigned, never to what a person did."""
        txn = make_transaction(household, source, "SOMETHING ONLY I UNDERSTAND")
        txn.category = food
        txn.is_categorised_by_user = True
        txn.save()

        result = categorise_transactions(household)

        txn.refresh_from_db()
        assert txn.category_id == food.pk
        assert result.cleared == 0
