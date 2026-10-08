"""The rules API: suggesting a rule, previewing it, and creating it.

Exercised over HTTP because the value of these endpoints is the shape of what
they return — a suggestion the UI cannot render is not a suggestion.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.categories.models import Category
from apps.rules.models import CategoryRule
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def household(user):
    return user.default_household


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="ICICI", kind=Source.Kind.BANK)


@pytest.fixture
def food(household):
    return Category.objects.for_household(household).get(name="Eating Out")


def make_transaction(household, source, description, amount="-250.00", day=3):
    return Transaction.objects.create(
        household=household,
        source=source,
        txn_date=date(2024, 4, day),
        description=description,
        amount=Decimal(amount),
    )


class TestSuggestingARule:
    def test_prefers_the_upi_vpa(self, client, household, source) -> None:
        make_transaction(household, source, "UPI/SWIGGY/swiggy@examplebank/Order")

        response = client.get(
            "/api/rules/suggest/", {"description": "UPI/SWIGGY/swiggy@examplebank/Order"}
        )

        assert response.status_code == 200
        assert response.data["match_type"] == CategoryRule.MatchType.UPI_VPA
        assert response.data["pattern"] == "swiggy@examplebank"

    def test_falls_back_to_the_distinctive_word(self, client, household, source) -> None:
        """The same fragment the app would have learned on its own."""
        description = "CHAI HAI NA UPI/CHAI HAI N/paytm.d1088744/UPI/AXIS"
        make_transaction(household, source, description)

        response = client.get("/api/rules/suggest/", {"description": description})

        assert response.data["match_type"] == CategoryRule.MatchType.CONTAINS
        assert response.data["pattern"] == "CHAI"

    def test_falls_back_to_the_whole_description_when_nothing_stands_out(
        self, client, household, source
    ) -> None:
        """Where learning gives up, an explicit rule can still be narrow but valid.

        `learn_from_recategorisation` returns None here — a rule this narrow is
        not worth writing unprompted. Asked for one directly, refusing to answer
        would be unhelpful.
        """
        response = client.get("/api/rules/suggest/", {"description": "NEFT DR 123456"})

        assert response.data["match_type"] == CategoryRule.MatchType.EXACT
        assert response.data["pattern"] == "NEFT DR 123456"

    def test_shows_what_else_the_rule_would_catch(self, client, household, source) -> None:
        """The preview is the safeguard against an over-broad pattern."""
        make_transaction(household, source, "CHAI HAI NA UPI/CHAI HAI N", day=3)
        make_transaction(household, source, "CHAI POINT BENGALURU", day=4)
        make_transaction(household, source, "BIG BAZAAR GROCERY", day=5)

        response = client.get("/api/rules/suggest/", {"description": "CHAI HAI NA UPI/CHAI HAI N"})

        assert response.data["matches"] == 2
        assert {row["description"] for row in response.data["examples"]} == {
            "CHAI HAI NA UPI/CHAI HAI N",
            "CHAI POINT BENGALURU",
        }

    def test_counts_only_this_households_transactions(self, client, source, household) -> None:
        other = User.objects.create_user(
            email="raj@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        other_source = Source.objects.create(household=other, name="HDFC", kind=Source.Kind.BANK)
        make_transaction(household, source, "CHAI POINT BENGALURU")
        make_transaction(other, other_source, "CHAI POINT MUMBAI")

        response = client.get("/api/rules/suggest/", {"description": "CHAI POINT BENGALURU"})

        assert response.data["matches"] == 1

    def test_rejects_an_empty_description(self, client) -> None:
        assert client.get("/api/rules/suggest/").status_code == 400


class TestCreatingARule:
    def test_applies_immediately_to_existing_transactions(
        self, client, household, source, food
    ) -> None:
        """A rule that does nothing until the next import reads as broken."""
        txn = make_transaction(household, source, "CHAI POINT BENGALURU")

        response = client.post(
            "/api/rules/",
            {"category": food.pk, "match_type": "contains", "pattern": "CHAI POINT"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["applied"] >= 1
        txn.refresh_from_db()
        assert txn.category_id == food.pk

    def test_is_the_users_own_rule_regardless_of_what_was_posted(
        self, client, household, food
    ) -> None:
        """Origin decides priority, so accepting it from the client is a footgun.

        A rule posted as `builtin` would sort below rules the user never wrote.
        """
        response = client.post(
            "/api/rules/",
            {
                "category": food.pk,
                "match_type": "contains",
                "pattern": "CHAI POINT",
                "origin": "builtin",
            },
            format="json",
        )

        rule = CategoryRule.objects.get(pk=response.data["id"])
        assert rule.origin == CategoryRule.Origin.USER
        assert rule.priority == CategoryRule.DEFAULT_PRIORITY[CategoryRule.Origin.USER]

    def test_rejects_an_invalid_regex_with_400(self, client, food) -> None:
        """Model validation raises Django's ValidationError, which is a 500 unless caught."""
        response = client.post(
            "/api/rules/",
            {"category": food.pk, "match_type": "regex", "pattern": "CHAI("},
            format="json",
        )

        assert response.status_code == 400
        assert "pattern" in response.data

    def test_rejects_another_households_category(self, client, food) -> None:
        other = User.objects.create_user(
            email="raj@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        theirs = Category.objects.for_household(other).get(name="Eating Out")

        response = client.post(
            "/api/rules/",
            {"category": theirs.pk, "match_type": "contains", "pattern": "CHAI"},
            format="json",
        )

        assert response.status_code == 400


class TestListingRules:
    def test_never_leaks_another_households_rules(self, client, household, food) -> None:
        other = User.objects.create_user(
            email="raj@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        theirs = Category.objects.for_household(other).get(name="Eating Out")
        CategoryRule.objects.create(household=other, category=theirs, pattern="SECRET")

        response = client.get("/api/rules/")

        patterns = {rule["pattern"] for rule in response.data["results"]}
        assert "SECRET" not in patterns

    def test_can_be_switched_off(self, client, household, food, source) -> None:
        """A wrong rule the user cannot disable is worse than no rule."""
        rule = CategoryRule.objects.create(household=household, category=food, pattern="CHAI")

        response = client.patch(f"/api/rules/{rule.pk}/", {"is_active": False}, format="json")

        assert response.status_code == 200
        rule.refresh_from_db()
        assert rule.is_active is False

    def test_serialises_the_match_type_for_display(self, client, household, food) -> None:
        CategoryRule.objects.create(
            household=household,
            category=food,
            match_type=CategoryRule.MatchType.UPI_VPA,
            pattern="swiggy@examplebank",
        )

        payload = json.loads(client.get("/api/rules/").content)
        rule = next(r for r in payload["results"] if r["pattern"] == "swiggy@examplebank")

        assert rule["match_type_label"] == "UPI VPA is"
        assert rule["category_name"] == food.full_name


class TestPreviewingAnEditedPattern:
    """The suggestion is a starting point; the user can widen or narrow it."""

    def test_previews_the_pattern_the_user_typed(self, client, household, source) -> None:
        make_transaction(household, source, "CHAI POINT BENGALURU", day=3)
        make_transaction(household, source, "CHAI HAI NA", day=4)

        response = client.get("/api/rules/suggest/", {"pattern": "CHAI POINT"})

        assert response.data["matches"] == 1
        assert response.data["pattern"] == "CHAI POINT"

    def test_honours_the_match_type(self, client, household, source) -> None:
        make_transaction(household, source, "CHAI POINT BENGALURU")

        contains = client.get("/api/rules/suggest/", {"pattern": "CHAI", "match_type": "contains"})
        exact = client.get("/api/rules/suggest/", {"pattern": "CHAI", "match_type": "exact"})

        assert contains.data["matches"] == 1
        assert exact.data["matches"] == 0

    def test_rejects_a_bad_regex_rather_than_reporting_no_matches(self, client) -> None:
        """`matches()` swallows a broken regex, which would preview as a working
        rule that happens to catch nothing."""
        response = client.get("/api/rules/suggest/", {"pattern": "CHAI(", "match_type": "regex"})

        assert response.status_code == 400
        assert "pattern" in response.data

    def test_rejects_an_unknown_match_type(self, client) -> None:
        response = client.get("/api/rules/suggest/", {"pattern": "CHAI", "match_type": "vibes"})

        assert response.status_code == 400


class TestHandFiledTransactionsAreNotPromised:
    """A rule does not overrule a person, so the preview must not claim it will."""

    def test_counts_them_separately(self, client, household, source, food) -> None:
        make_transaction(household, source, "CHAI POINT BENGALURU", day=3)
        mine = make_transaction(household, source, "CHAI POINT MUMBAI", day=4)
        mine.category = food
        mine.is_categorised_by_user = True
        mine.save()

        response = client.get("/api/rules/suggest/", {"pattern": "CHAI POINT"})

        assert response.data["matches"] == 2
        assert response.data["protected"] == 1

    def test_and_creating_the_rule_leaves_them_alone(self, client, household, source, food) -> None:
        groceries = Category.objects.for_household(household).get(name="Groceries")
        mine = make_transaction(household, source, "CHAI POINT MUMBAI")
        mine.category = groceries
        mine.is_categorised_by_user = True
        mine.save()

        client.post(
            "/api/rules/",
            {"category": food.pk, "match_type": "contains", "pattern": "CHAI POINT"},
            format="json",
        )

        mine.refresh_from_db()
        assert mine.category_id == groceries.pk
