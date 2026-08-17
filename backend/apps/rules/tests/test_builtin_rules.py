"""The bundled merchant patterns.

The false-positive tests below are the important ones. A pattern that fires
inside a longer word files a transaction wrongly and says nothing about it —
the user just sees their salary categorised as a credit-card payment. Every
risky short pattern in builtin_patterns.yaml should have a case here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import Household, User
from apps.categories.models import Category
from apps.rules.builtin import load_patterns, seed_builtin_rules
from apps.rules.engine import active_rules, categorise, categorise_transactions
from apps.rules.models import CategoryRule
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    return User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="HDFC", kind=Source.Kind.BANK)


def categorise_description(household, description: str) -> str | None:
    """The category a fresh household would file this description under."""
    rule = categorise(description, active_rules(household))
    return rule.category.full_name if rule else None


class TestPatternFile:
    def test_patterns_load(self) -> None:
        assert len(load_patterns()) > 80

    def test_every_category_path_resolves(self, household) -> None:
        """A typo in a path would silently drop that merchant, so every path in
        the file must exist in the default taxonomy."""
        unresolved = []
        for entry in load_patterns():
            parent = None
            for name in entry.category_path:
                match = (
                    Category.objects.for_household(household)
                    .filter(name=name, parent=parent)
                    .first()
                )
                if match is None:
                    unresolved.append(f"{entry.pattern}: {' > '.join(entry.category_path)}")
                    break
                parent = match

        assert not unresolved, "category paths not found in the default taxonomy:\n" + "\n".join(
            unresolved
        )

    def test_regex_patterns_compile(self) -> None:
        import re

        for entry in load_patterns():
            if entry.match_type == CategoryRule.MatchType.REGEX:
                re.compile(entry.pattern)

    def test_no_contains_pattern_hides_inside_a_common_word(self) -> None:
        """The guard that keeps the file safe to extend.

        Length alone is the wrong test — UBER and IRCTC are short and perfectly
        safe. The actual hazard is a pattern that is a *substring of a word
        that appears in ordinary narrations*, which is how CRED ends up
        matching every salary credit. So that is what's checked.
        """
        common_narration_words = [
            "ACCOUNT",
            "BALANCE",
            "BRANCH",
            "CHARGES",
            "CHOCOLATE",
            "CLOSING",
            "CREDIT",
            "DEBIT",
            "DEPOSIT",
            "ELECTRICITY",
            "INSURANCE",
            "INTEREST",
            "MERCHANT",
            "MOTOROLA",
            "OPENING",
            "PAYMENT",
            "POLICY",
            "PREMIUM",
            "PUBLIC",
            "PURCHASE",
            "RECHARGE",
            "REVERSAL",
            "SALARY",
            "SETTLEMENT",
            "STATEMENT",
            "TRANSACTION",
            "TRANSFER",
            "WITHDRAWAL",
        ]

        collisions = [
            (entry.pattern, word)
            for entry in load_patterns()
            if entry.match_type == CategoryRule.MatchType.CONTAINS
            for word in common_narration_words
            if entry.pattern.upper() in word and entry.pattern.upper() != word
        ]

        assert not collisions, (
            "These `contains` patterns appear inside ordinary narration words and "
            f"will file transactions wrongly: {collisions}. "
            "Use `match: regex` with \\b on both sides."
        )


class TestSeeding:
    def test_a_new_household_gets_the_bundled_rules(self, household) -> None:
        """A first upload should categorise well before the user configures
        anything."""
        rules = CategoryRule.objects.for_household(household)
        assert rules.count() == len(load_patterns())
        assert all(r.origin == CategoryRule.Origin.BUILTIN for r in rules)

    def test_bundled_rules_are_the_lowest_priority(self, household) -> None:
        rule = CategoryRule.objects.for_household(household).first()
        assert rule.priority == CategoryRule.DEFAULT_PRIORITY[CategoryRule.Origin.BUILTIN]

    def test_reseeding_creates_nothing_new(self, household) -> None:
        before = CategoryRule.objects.for_household(household).count()
        assert seed_builtin_rules(household) == 0
        assert CategoryRule.objects.for_household(household).count() == before

    def test_reseeding_respects_a_deactivated_rule(self, household) -> None:
        """Backfilling new merchants must not resurrect one the user turned off."""
        rule = CategoryRule.objects.for_household(household).get(pattern="SWIGGY")
        rule.is_active = False
        rule.save()

        seed_builtin_rules(household)

        rule.refresh_from_db()
        assert rule.is_active is False

    def test_reseeding_respects_a_recategorised_merchant(self, household) -> None:
        rule = CategoryRule.objects.for_household(household).get(pattern="SWIGGY")
        groceries = Category.objects.for_household(household).get(name="Groceries")
        rule.category = groceries
        rule.save()

        seed_builtin_rules(household)

        rule.refresh_from_db()
        assert rule.category == groceries

    def test_missing_category_paths_are_skipped_not_fatal(self) -> None:
        """A household that pruned its tree still gets the rules that resolve.

        Seeding must degrade rather than fail: a renamed or deleted branch
        should cost you those merchants, not every merchant.
        """
        household = Household.objects.create(name="Bare")
        # Creating a household seeds the full tree and its rules; strip both
        # back to a single top-level category to model a heavily pruned tree.
        CategoryRule.objects.for_household(household).delete()
        Category.objects.for_household(household).delete()
        Category.objects.create(household=household, name="Cash Withdrawal")

        created = seed_builtin_rules(household)

        # Only the patterns pointing at "Cash Withdrawal" can resolve.
        assert 0 < created < len(load_patterns())
        assert all(
            rule.category.name == "Cash Withdrawal"
            for rule in CategoryRule.objects.for_household(household)
        )

    def test_rules_never_cross_households(self, household) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household

        mine = CategoryRule.objects.for_household(household).get(pattern="SWIGGY")
        theirs = CategoryRule.objects.for_household(other).get(pattern="SWIGGY")

        assert mine.pk != theirs.pk


class TestRealNarrations:
    """Descriptions in the shape Indian banks actually print them."""

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT", "Food & Dining > Eating Out > Food Delivery"),
            (
                "UPI-ZOMATO LTD-ZOMATO@EXAMPLEBANK-ORDER",
                "Food & Dining > Eating Out > Food Delivery",
            ),
            ("UPI-BIGBASKET-BB@EXAMPLEBANK-GROCERY", "Food & Dining > Groceries > Online Grocery"),
            ("POS 000000000000 IRCTC ONLINE", "Transport > Public Transport > Train"),
            ("UPI-UBER INDIA-UBER@EXAMPLEBANK", "Transport > Cabs & Autos"),
            ("POS INDIAN OIL CORP TEST CITY", "Transport > Fuel"),
            ("NETFLIX COM MUMBAI IN", "Entertainment > Subscriptions > Streaming"),
            ("MYNTRA DESIGNS BANGALORE IN", "Shopping > Clothing"),
            ("ATW-XXXXXXXX1234-TEST BRANCH ATM", "Cash Withdrawal"),
            ("SALARY CREDIT TESTCORP PVT LTD", "Income > Salary"),
            ("INT.CR-SAVINGS INTEREST", "Income > Interest & Dividends"),
        ],
    )
    def test_common_merchants_are_categorised(
        self, household, description: str, expected: str
    ) -> None:
        actual = categorise_description(household, description)
        assert actual is not None, f"{description!r} matched no bundled rule"
        assert actual.replace(" → ", " > ") == expected

    def test_a_real_statement_lands_mostly_categorised(self, household, source) -> None:
        """The whole point: a first upload should not be a wall of
        "Uncategorised"."""
        descriptions = [
            "SALARY CREDIT TESTCORP PVT LTD",
            "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAYMENT",
            "ACH D- HDFC LIFE INSURANCE",
            "UPI-BIGBASKET-BB@EXAMPLEBANK-GROCERY",
            "NEFT DR-BANK0000000-RAHUL K-RENT APRIL",
            "POS 000000000000 IRCTC ONLINE",
            "UPI-AMAZON PAY INDIA-AMZN@EXAMPLEBANK",
            "INT.CR-SAVINGS INTEREST",
            "ATW-XXXXXXXX1234-TEST BRANCH ATM",
            "UPI-ASHA S-ASHA@EXAMPLEBANK-SPLIT DINNER",
        ]
        for index, description in enumerate(descriptions):
            Transaction.objects.create(
                household=household,
                source=source,
                txn_date=date(2024, 4, index + 1),
                description=description,
                amount=Decimal("-100.00"),
            )

        result = categorise_transactions(household)

        # Six of these ten are recognisable merchants; the rest (a rent
        # transfer, a person-to-person split, an Amazon Pay load) genuinely
        # need the user to say what they are.
        assert result.categorised >= 6


class TestFalsePositives:
    """Short patterns that would fire inside ordinary banking words.

    Each of these was a real hazard in the pattern file. They fail silently
    when wrong — the transaction is simply filed under the wrong category — so
    they are pinned explicitly.
    """

    @pytest.mark.parametrize(
        ("description", "must_not_be"),
        [
            # CRED is inside CREDIT, which appears on nearly every salary line.
            ("SALARY CREDIT TESTCORP PVT LTD", "Financial > Credit Card Payment"),
            ("NEFT CREDIT FROM RAHUL K", "Financial > Credit Card Payment"),
            ("INT.CR-SAVINGS INTEREST CREDITED", "Financial > Credit Card Payment"),
            # LIC is inside POLICY and PUBLIC.
            ("POS PUBLIC LIBRARY MEMBERSHIP", "Financial > Insurance Premiums"),
            ("UPI-POLICY RENEWAL-XYZ@EXAMPLEBANK", "Financial > Insurance Premiums"),
            # OLA is inside MOTOROLA and CHOCOLATE.
            ("POS MOTOROLA MOBILITY INDIA", "Transport > Cabs & Autos"),
            ("UPI-CHOCOLATE ROOM-CHOC@EXAMPLEBANK", "Transport > Cabs & Autos"),
            # JIO is inside JIOMART, which is groceries rather than connectivity.
            ("UPI-JIOMART-JIO@EXAMPLEBANK-GROCERY", "Housing > Utilities > Internet & Mobile"),
        ],
    )
    def test_short_patterns_do_not_fire_inside_longer_words(
        self, household, description: str, must_not_be: str
    ) -> None:
        actual = categorise_description(household, description)
        normalised = actual.replace(" → ", " > ") if actual else None
        assert normalised != must_not_be, (
            f"{description!r} was filed as {must_not_be} — a short pattern matched "
            "inside a longer word. Use `match: regex` with word boundaries."
        )

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("UPI-CRED-CRED@AXISB-CARD PAYMENT", "Financial > Credit Card Payment"),
            ("ACH D- LIC OF INDIA PREMIUM", "Financial > Insurance Premiums"),
            ("UPI-OLA CABS-OLA@EXAMPLEBANK", "Transport > Cabs & Autos"),
        ],
    )
    def test_the_word_boundary_versions_still_match(
        self, household, description: str, expected: str
    ) -> None:
        """Guarding against false positives must not break the real case."""
        actual = categorise_description(household, description)
        assert actual is not None, f"{description!r} matched no rule"
        assert actual.replace(" → ", " > ") == expected


class TestPrecedenceOverBundledRules:
    def test_a_users_correction_beats_the_bundled_rule(self, household, source) -> None:
        """Someone who files Swiggy under Groceries should keep it that way."""
        transaction = Transaction.objects.create(
            household=household,
            source=source,
            txn_date=date(2024, 4, 3),
            description="UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAY",
            amount=Decimal("-450.00"),
        )
        groceries = Category.objects.for_household(household).get(name="Groceries")

        from apps.rules.engine import learn_from_recategorisation

        learn_from_recategorisation(transaction, groceries)
        categorise_transactions(household)

        transaction.refresh_from_db()
        assert transaction.category == groceries
