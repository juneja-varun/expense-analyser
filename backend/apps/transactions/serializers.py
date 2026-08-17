from __future__ import annotations

from rest_framework import serializers

from apps.categories.models import Category
from apps.transactions.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    # `default=None` matters: without it DRF drops these keys entirely when the
    # category is null, so an uncategorised transaction has a different set of
    # fields from a categorised one. A client then has to handle "absent" and
    # "null" separately for no reason.
    category_name = serializers.CharField(source="category.full_name", read_only=True, default=None)
    category_colour = serializers.CharField(source="category.colour", read_only=True, default=None)
    source_name = serializers.CharField(source="source.name", read_only=True, default=None)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "txn_date",
            "value_date",
            "description",
            "amount",
            "balance",
            "reference",
            "notes",
            "category",
            "category_name",
            "category_colour",
            "source",
            "source_name",
            "is_categorised_by_user",
            "created_at",
        ]
        # Everything from the statement is immutable: a transaction is a record
        # of what the bank said, not something the user edits. Only the
        # category and their own notes can change.
        read_only_fields = [
            "txn_date",
            "value_date",
            "description",
            "amount",
            "balance",
            "reference",
            "source",
            "is_categorised_by_user",
            "created_at",
        ]

    def validate_category(self, category: Category | None) -> Category | None:
        if category is None:
            return None
        household = self.context["request"].user.default_household
        if category.household_id != household.pk:
            raise serializers.ValidationError("That category belongs to another household.")
        return category
