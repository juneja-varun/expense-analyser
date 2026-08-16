from __future__ import annotations

import pytest

from apps.accounts.models import Household, User
from apps.categories.models import MAX_DEPTH, Category
from apps.categories.services import get_uncategorised, seed_default_categories

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    return User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household


class TestAutomaticSeeding:
    def test_registering_gives_the_user_a_category_tree(self, household) -> None:
        """A first upload should land in sensible buckets before the user has
        configured anything."""
        assert Category.objects.for_household(household).count() > 40

    def test_seeds_both_spending_and_income_branches(self, household) -> None:
        categories = Category.objects.for_household(household)
        assert categories.filter(name="Food & Dining", is_income=False).exists()
        assert categories.filter(name="Income", is_income=True).exists()

    def test_income_flag_propagates_to_children(self, household) -> None:
        salary = Category.objects.for_household(household).get(name="Salary")
        assert salary.is_income is True
        assert salary.parent.name == "Income"

    def test_tree_never_exceeds_three_levels(self, household) -> None:
        deepest = max(c.depth for c in Category.objects.for_household(household))
        assert deepest == MAX_DEPTH

    def test_third_level_rolls_up_to_a_top_level_root(self, household) -> None:
        food_delivery = Category.objects.for_household(household).get(name="Food Delivery")
        assert food_delivery.depth == 2
        assert food_delivery.root.name == "Food & Dining"
        assert food_delivery.full_name == "Food & Dining → Eating Out → Food Delivery"

    def test_seeded_categories_are_marked_as_system(self, household) -> None:
        assert not Category.objects.for_household(household).filter(is_system=False).exists()

    def test_seeding_failure_does_not_break_registration(self, monkeypatch) -> None:
        """A household with no categories is recoverable; a user who could not
        register is not."""
        monkeypatch.setattr(
            "apps.categories.services.seed_default_categories",
            lambda household: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        user = User.objects.create_user(email="rahul@example.com", password="corr3ct-h0rse-b4ttery")
        assert user.pk is not None


class TestIdempotency:
    def test_reseeding_creates_nothing_new(self, household) -> None:
        before = Category.objects.for_household(household).count()
        assert seed_default_categories(household) == 0
        assert Category.objects.for_household(household).count() == before

    def test_reseeding_preserves_user_edits(self, household) -> None:
        """Backfilling a later release's new categories must not undo renames."""
        food = Category.objects.for_household(household).get(name="Food & Dining")
        food.name = "Food, glorious food"
        food.save()

        seed_default_categories(household)

        food.refresh_from_db()
        assert food.name == "Food, glorious food"

    def test_missing_branch_is_restored_without_touching_others(self, household) -> None:
        Category.objects.for_household(household).filter(name="Health").delete()
        transport = Category.objects.for_household(household).get(name="Transport")

        created = seed_default_categories(household)

        assert created > 0
        assert Category.objects.for_household(household).filter(name="Health").exists()
        assert Category.objects.for_household(household).get(name="Transport").pk == transport.pk


class TestUncategorised:
    def test_seeded_by_default(self, household) -> None:
        assert Category.objects.for_household(household).filter(name="Uncategorised").exists()

    def test_recreated_on_demand_if_the_user_deletes_it(self, household) -> None:
        Category.objects.for_household(household).filter(name="Uncategorised").delete()

        category = get_uncategorised(household)

        assert category.name == "Uncategorised"
        assert category.is_system is True

    def test_returns_the_existing_one_rather_than_duplicating(self, household) -> None:
        first = get_uncategorised(household)
        assert get_uncategorised(household).pk == first.pk


class TestHouseholdIsolation:
    def test_each_household_gets_its_own_tree(self, household) -> None:
        other = Household.objects.create(name="Another household")
        seed_default_categories(other)

        asha_food = Category.objects.for_household(household).get(name="Food & Dining")
        other_food = Category.objects.for_household(other).get(name="Food & Dining")

        assert asha_food.pk != other_food.pk
