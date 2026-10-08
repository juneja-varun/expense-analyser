from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.categories.models import Category
from apps.rules.models import CategoryRule


class CategoryRuleSerializer(serializers.ModelSerializer):
    # `default=None` matters: with `source=` alone DRF omits the key entirely
    # when the relation is null, so a rule with no category would serialise to
    # a different shape than one with a category.
    category_name = serializers.CharField(source="category.full_name", read_only=True, default=None)
    match_type_label = serializers.CharField(source="get_match_type_display", read_only=True)

    class Meta:
        model = CategoryRule
        fields = [
            "id",
            "category",
            "category_name",
            "match_type",
            "match_type_label",
            "pattern",
            "origin",
            "priority",
            "is_active",
            "match_count",
        ]
        # Origin is not user-settable: a rule created through the API is by
        # definition the user's, and claiming to be BUILTIN would quietly
        # demote its priority below rules they never wrote.
        read_only_fields = ["origin", "match_count"]

    def validate_category(self, category: Category) -> Category:
        household = self.context["request"].user.default_household
        if category.household_id != household.pk:
            raise serializers.ValidationError("That category belongs to another household.")
        return category

    def validate(self, attrs: dict) -> dict:
        """Run the model's own validation so the API rejects what the DB would.

        `CategoryRule.save()` calls `clean()`, which raises Django's
        ValidationError — that surfaces as a 500 rather than a 400 unless it is
        caught here first. An invalid regex is a user mistake, not a bug.
        """
        instance = CategoryRule(
            **{
                **{
                    field: getattr(self.instance, field, None)
                    for field in ("category", "match_type", "pattern")
                },
                **attrs,
            }
        )
        instance.household = self.context["request"].user.default_household
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs
