from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import User
from apps.categories.models import Category

pytestmark = pytest.mark.django_db


@pytest.fixture
def household():
    return User.objects.create_user(
        email="asha@example.com", password="corr3ct-h0rse-b4ttery"
    ).default_household


@pytest.fixture
def food(household):
    return Category.objects.create(household=household, name="Food & Dining")


class TestTreeStructure:
    def test_root_category_has_no_parent_and_zero_depth(self, food) -> None:
        assert food.parent is None
        assert food.depth == 0
        assert food.root is None
        assert food.effective_root == food

    def test_child_records_depth_and_root(self, household, food) -> None:
        eating_out = Category.objects.create(household=household, name="Eating Out", parent=food)
        assert eating_out.depth == 1
        assert eating_out.root == food

    def test_grandchild_points_at_the_top_level_root(self, household, food) -> None:
        """The denormalisation that makes roll-ups a single join: a third-level
        category's `root` is the top level, not its immediate parent."""
        eating_out = Category.objects.create(household=household, name="Eating Out", parent=food)
        weekend = Category.objects.create(household=household, name="Weekend", parent=eating_out)

        assert weekend.depth == 2
        assert weekend.root == food
        assert weekend.parent == eating_out

    def test_full_name_is_a_breadcrumb(self, household, food) -> None:
        eating_out = Category.objects.create(household=household, name="Eating Out", parent=food)
        weekend = Category.objects.create(household=household, name="Weekend", parent=eating_out)
        assert weekend.full_name == "Food & Dining → Eating Out → Weekend"

    def test_roll_up_by_root_finds_the_whole_subtree(self, household, food) -> None:
        eating_out = Category.objects.create(household=household, name="Eating Out", parent=food)
        Category.objects.create(household=household, name="Weekend", parent=eating_out)
        Category.objects.create(household=household, name="Groceries", parent=food)

        assert food.descendants.count() == 3


class TestDepthLimit:
    def test_rejects_a_fourth_level(self, household, food) -> None:
        level_two = Category.objects.create(household=household, name="Eating Out", parent=food)
        level_three = Category.objects.create(household=household, name="Weekend", parent=level_two)

        with pytest.raises(ValidationError, match="at most 3 levels"):
            Category.objects.create(household=household, name="Too deep", parent=level_three)


class TestValidation:
    def test_parent_must_be_in_the_same_household(self, household, food) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household

        with pytest.raises(ValidationError, match="different household"):
            Category.objects.create(household=other, name="Eating Out", parent=food)

    def test_category_cannot_be_its_own_parent(self, food) -> None:
        food.parent = food
        with pytest.raises(ValidationError, match="own parent"):
            food.save()

    def test_reparenting_cannot_create_a_loop(self, household, food) -> None:
        child = Category.objects.create(household=household, name="Eating Out", parent=food)
        food.parent = child
        with pytest.raises(ValidationError, match="loop"):
            food.save()

    def test_sibling_names_must_be_unique(self, household, food) -> None:
        Category.objects.create(household=household, name="Groceries", parent=food)
        with pytest.raises(IntegrityError):
            Category.objects.create(household=household, name="Groceries", parent=food)

    def test_same_name_is_fine_under_different_parents(self, household, food) -> None:
        """ "Other" under Food and "Other" under Transport are different things."""
        transport = Category.objects.create(household=household, name="Transport")
        Category.objects.create(household=household, name="Other", parent=food)
        Category.objects.create(household=household, name="Other", parent=transport)

        assert Category.objects.filter(name="Other").count() == 2

    def test_two_households_can_use_the_same_category_name(self, household, food) -> None:
        other = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        Category.objects.create(household=other, name="Food & Dining")

        assert Category.objects.filter(name="Food & Dining").count() == 2


class TestHouseholdIsolation:
    def test_scoping_excludes_other_households(self, household, food) -> None:
        rahul = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        )
        Category.objects.create(household=rahul.default_household, name="Transport")

        visible = Category.objects.for_household(household)
        assert list(visible) == [food]
