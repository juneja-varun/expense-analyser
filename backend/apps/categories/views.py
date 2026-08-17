from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.categories.models import Category
from apps.categories.serializers import CategorySerializer
from apps.common.views import HouseholdScopedViewSet


class CategoryViewSet(HouseholdScopedViewSet):
    """The household's category tree.

    Returned flat with `parent`/`depth`/`root` rather than nested: the client
    needs both the tree (for pickers) and flat lookups (for the transaction
    list), and rebuilding a flat index from nested JSON is more work than the
    reverse.
    """

    serializer_class = CategorySerializer
    queryset = Category.objects.select_related("parent").order_by("sort_order", "name")

    def get_queryset(self):
        return (
            super().get_queryset().annotate(transaction_count=Count("transactions", distinct=True))
        )

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Deleting a category must not take its transactions with it.

        `Transaction.category` is SET_NULL, so the rows survive and simply
        become uncategorised — but a seeded category is a different matter: the
        rest of the app assumes the default tree exists.
        """
        category = self.get_object()

        if category.is_system:
            return Response(
                {
                    "detail": (
                        "This is a built-in category. You can rename it, but deleting it "
                        "would break the default tree — hide it instead if you don't use it."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def tree(self, request: Request) -> Response:
        """The same categories, nested — convenient for pickers and charts."""
        categories = list(self.get_queryset())
        by_parent: dict[int | None, list] = {}
        for category in categories:
            by_parent.setdefault(category.parent_id, []).append(category)

        def build(parent_id: int | None) -> list[dict]:
            return [
                {
                    **CategorySerializer(child, context=self.get_serializer_context()).data,
                    "children": build(child.pk),
                }
                for child in by_parent.get(parent_id, [])
            ]

        return Response(build(None))

    @action(detail=False, methods=["get"])
    def unused(self, request: Request) -> Response:
        """Categories nothing has ever been filed under.

        Surfaces the parts of the seeded taxonomy a household doesn't need, so
        they can prune it rather than scrolling past forty empty options.
        """
        empty = self.get_queryset().filter(Q(transaction_count=0))
        return Response(self.get_serializer(empty, many=True).data)
