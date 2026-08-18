from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.budgets.models import Budget
from apps.budgets.services import budget_progress
from apps.categories.models import Category
from apps.common.dates import add_months, first_of_month
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db

APRIL = date(2024, 4, 1)


@pytest.fixture
def user():
    return User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")


@pytest.fixture
def household(user):
    return user.default_household


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="HDFC", kind=Source.Kind.BANK)


def category(household, name: str) -> Category:
    return Category.objects.for_household(household).get(name=name)


def spend(household, source, category_obj, amount: str, day: int = 3) -> Transaction:
    return Transaction.objects.create(
        household=household,
        source=source,
        category=category_obj,
        txn_date=date(2024, 4, day),
        description=f"SPEND {category_obj.name}",
        amount=Decimal(amount),
    )


class TestMonthArithmetic:
    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            (date(2024, 4, 15), 1, date(2024, 5, 1)),
            (date(2024, 12, 1), 1, date(2025, 1, 1)),
            (date(2024, 1, 31), -1, date(2023, 12, 1)),
            (date(2024, 3, 1), -3, date(2023, 12, 1)),
        ],
    )
    def test_add_months(self, start: date, months: int, expected: date) -> None:
        assert add_months(start, months) == expected

    def test_first_of_month(self) -> None:
        assert first_of_month(date(2024, 4, 30)) == APRIL


class TestBudgetModel:
    def test_month_is_normalised_to_the_first(self, household) -> None:
        """Any date in the month means that month — the day is noise."""
        budget = Budget.objects.create(
            household=household,
            category=category(household, "Food & Dining"),
            month=date(2024, 4, 17),
            amount=Decimal("10000.00"),
        )
        assert budget.month == APRIL

    def test_one_budget_per_category_per_month(self, household) -> None:
        food = category(household, "Food & Dining")
        Budget.objects.create(household=household, category=food, month=APRIL, amount=Decimal("1"))

        with pytest.raises(IntegrityError):
            Budget.objects.create(
                household=household, category=food, month=APRIL, amount=Decimal("2")
            )

    def test_the_same_category_can_be_budgeted_in_another_month(self, household) -> None:
        food = category(household, "Food & Dining")
        Budget.objects.create(household=household, category=food, month=APRIL, amount=Decimal("1"))
        Budget.objects.create(
            household=household, category=food, month=date(2024, 5, 1), amount=Decimal("2")
        )
        assert Budget.objects.for_household(household).count() == 2

    def test_income_categories_cannot_be_budgeted(self, household) -> None:
        """A budget caps spending; capping what you earn is meaningless."""
        with pytest.raises(ValidationError, match="Income categories"):
            Budget.objects.create(
                household=household,
                category=category(household, "Salary"),
                month=APRIL,
                amount=Decimal("100.00"),
            )

    def test_category_must_belong_to_the_same_household(self, household) -> None:
        stranger = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household

        with pytest.raises(ValidationError, match="different household"):
            Budget.objects.create(
                household=household,
                category=category(stranger, "Food & Dining"),
                month=APRIL,
                amount=Decimal("100.00"),
            )

    def test_negative_budgets_are_rejected(self, household) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            Budget.objects.create(
                household=household,
                category=category(household, "Food & Dining"),
                month=APRIL,
                amount=Decimal("-100.00"),
            )


class TestBudgetProgress:
    def test_spend_counts_against_its_own_category(self, household, source) -> None:
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-450.00")

        [progress] = budget_progress(household, APRIL)

        assert progress.budgeted == Decimal("2000.00")
        assert progress.spent == Decimal("450.00")
        assert progress.remaining == Decimal("1550.00")
        assert progress.percent_used == 23
        assert progress.is_over is False

    def test_a_parent_budget_covers_its_whole_subtree(self, household, source) -> None:
        """Budgeting "Food & Dining" means the whole branch — that is what a
        person means by it, and counting only transactions filed directly on
        the parent would show almost nothing."""
        Budget.objects.create(
            household=household,
            category=category(household, "Food & Dining"),
            month=APRIL,
            amount=Decimal("10000.00"),
        )
        spend(household, source, category(household, "Food Delivery"), "-450.00")
        spend(household, source, category(household, "Groceries"), "-2000.00", day=5)
        spend(household, source, category(household, "Restaurants"), "-1500.00", day=7)

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("3950.00")

    def test_spend_outside_the_subtree_is_excluded(self, household, source) -> None:
        Budget.objects.create(
            household=household,
            category=category(household, "Food & Dining"),
            month=APRIL,
            amount=Decimal("10000.00"),
        )
        spend(household, source, category(household, "Food Delivery"), "-450.00")
        spend(household, source, category(household, "Fuel"), "-3000.00", day=6)

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("450.00")

    def test_other_months_are_excluded(self, household, source) -> None:
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-450.00")
        Transaction.objects.create(
            household=household,
            source=source,
            category=delivery,
            txn_date=date(2024, 5, 3),
            description="MAY SPEND",
            amount=Decimal("-900.00"),
        )

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("450.00")

    def test_a_refund_reduces_the_months_spend(self, household, source) -> None:
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-450.00")
        spend(household, source, delivery, "150.00", day=9)

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("300.00")

    def test_a_category_that_nets_positive_shows_zero_not_negative(self, household, source) -> None:
        """A refund larger than the month's spend does not mean negative spend."""
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-100.00")
        spend(household, source, delivery, "500.00", day=9)

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("0.00")

    def test_going_over_is_reported_uncapped(self, household, source) -> None:
        """Clipping at 100% would hide how far over you are."""
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("1000.00")
        )
        spend(household, source, delivery, "-2500.00")

        [progress] = budget_progress(household, APRIL)

        assert progress.is_over is True
        assert progress.percent_used == 250
        assert progress.remaining == Decimal("-1500.00")

    def test_most_over_budget_comes_first(self, household, source) -> None:
        """What a person opens this screen to find."""
        for name, budgeted, spent in [
            ("Food Delivery", "1000.00", "-2500.00"),
            ("Fuel", "5000.00", "-1000.00"),
            ("Groceries", "3000.00", "-3200.00"),
        ]:
            cat = category(household, name)
            Budget.objects.create(
                household=household, category=cat, month=APRIL, amount=Decimal(budgeted)
            )
            spend(household, source, cat, spent)

        rows = budget_progress(household, APRIL)

        assert [r.category_name.split(" → ")[-1] for r in rows] == [
            "Food Delivery",
            "Groceries",
            "Fuel",
        ]

    def test_uncategorised_spend_counts_against_nothing(self, household, source) -> None:
        Budget.objects.create(
            household=household,
            category=category(household, "Food & Dining"),
            month=APRIL,
            amount=Decimal("10000.00"),
        )
        Transaction.objects.create(
            household=household,
            source=source,
            txn_date=date(2024, 4, 3),
            description="MYSTERY",
            amount=Decimal("-999.00"),
        )

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("0.00")

    def test_no_budgets_is_an_empty_list_not_an_error(self, household) -> None:
        assert budget_progress(household, APRIL) == []


class TestBudgetApi:
    def test_create_and_list(self, client, household) -> None:
        food = category(household, "Food & Dining")

        response = client.post(
            "/api/budgets/",
            {"category": food.pk, "month": "2024-04-01", "amount": "10000.00"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["category_name"] == "Food & Dining"
        assert client.get("/api/budgets/?month=2024-04").data["count"] == 1

    def test_progress_endpoint(self, client, household, source) -> None:
        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-450.00")

        response = client.get("/api/budgets/progress/?month=2024-04")

        assert response.status_code == 200
        assert response.data["total_budgeted"] == "2000.00"
        assert response.data["total_spent"] == "450.00"
        row = response.data["categories"][0]
        assert row["spent"] == "450.00"
        assert row["percent_used"] == 23

    def test_money_crosses_the_wire_as_strings(self, client, household, source) -> None:
        import json

        delivery = category(household, "Food Delivery")
        Budget.objects.create(
            household=household, category=delivery, month=APRIL, amount=Decimal("2000.00")
        )
        spend(household, source, delivery, "-0.10")
        spend(household, source, delivery, "-0.20", day=4)

        payload = json.loads(client.get("/api/budgets/progress/?month=2024-04").content)

        assert isinstance(payload["total_spent"], str)
        assert Decimal(payload["total_spent"]) == Decimal("0.30")

    def test_invalid_month_is_rejected_clearly(self, client) -> None:
        response = client.get("/api/budgets/progress/?month=April")

        assert response.status_code == 400
        assert "YYYY-MM" in str(response.data)

    def test_income_categories_are_rejected_by_the_api(self, client, household) -> None:
        response = client.post(
            "/api/budgets/",
            {"category": category(household, "Salary").pk, "month": "2024-04", "amount": "1.00"},
            format="json",
        )

        assert response.status_code == 400
        assert "Income categories" in str(response.data)

    def test_copy_from_previous_month(self, client, household) -> None:
        """Budgets are stable month to month; re-entering a dozen numbers is
        the chore that makes people give up on budgeting."""
        for name in ["Food & Dining", "Transport"]:
            Budget.objects.create(
                household=household,
                category=category(household, name),
                month=date(2024, 3, 1),
                amount=Decimal("5000.00"),
            )

        response = client.post(
            "/api/budgets/copy_from_previous_month/", {"month": "2024-04"}, format="json"
        )

        assert response.data["created"] == 2
        assert Budget.objects.for_household(household).filter(month=APRIL).count() == 2

    def test_copying_does_not_overwrite_what_is_already_set(self, client, household) -> None:
        food = category(household, "Food & Dining")
        Budget.objects.create(
            household=household, category=food, month=date(2024, 3, 1), amount=Decimal("5000.00")
        )
        Budget.objects.create(
            household=household, category=food, month=APRIL, amount=Decimal("9999.00")
        )

        response = client.post(
            "/api/budgets/copy_from_previous_month/", {"month": "2024-04"}, format="json"
        )

        assert response.data["created"] == 0
        april = Budget.objects.for_household(household).get(month=APRIL)
        assert april.amount == Decimal("9999.00")


class TestHouseholdIsolation:
    def test_budgets_never_cross_households(self, client, household) -> None:
        stranger = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        theirs = Budget.objects.create(
            household=stranger,
            category=category(stranger, "Food & Dining"),
            month=APRIL,
            amount=Decimal("7777.00"),
        )

        assert client.get("/api/budgets/").data["count"] == 0
        assert client.get(f"/api/budgets/{theirs.pk}/").status_code == 404

    def test_progress_only_counts_your_own_spend(self, household, source) -> None:
        stranger_user = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        )
        stranger = stranger_user.default_household
        stranger_source = Source.objects.create(
            household=stranger, name="Theirs", kind=Source.Kind.BANK
        )
        Budget.objects.create(
            household=household,
            category=category(household, "Food & Dining"),
            month=APRIL,
            amount=Decimal("10000.00"),
        )
        spend(stranger, stranger_source, category(stranger, "Food Delivery"), "-5000.00")

        [progress] = budget_progress(household, APRIL)

        assert progress.spent == Decimal("0.00")
