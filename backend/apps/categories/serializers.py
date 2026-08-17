from __future__ import annotations

from rest_framework import serializers

from apps.categories.models import MAX_DEPTH, Category


class CategorySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    transaction_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "full_name",
            "parent",
            "root",
            "depth",
            "colour",
            "icon",
            "is_income",
            "is_system",
            "sort_order",
            "transaction_count",
        ]
        read_only_fields = ["root", "depth", "is_system", "full_name"]

    def validate_parent(self, parent: Category | None) -> Category | None:
        if parent is None:
            return None

        household = self.context["request"].user.default_household
        if parent.household_id != household.pk:
            raise serializers.ValidationError("That category belongs to another household.")

        if parent.depth >= MAX_DEPTH:
            raise serializers.ValidationError(
                f"Categories nest at most {MAX_DEPTH + 1} levels deep."
            )
        return parent
