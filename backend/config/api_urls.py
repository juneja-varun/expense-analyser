"""The v1 API surface.

Kept in one file so the whole API is visible at a glance — with a router per
app the routes end up scattered across seven modules for no benefit at this
size.
"""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.categories.views import CategoryViewSet
from apps.sources.views import SourceViewSet
from apps.statements.views import StatementViewSet
from apps.transactions.views import TransactionViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("statements", StatementViewSet, basename="statement")
router.register("sources", SourceViewSet, basename="source")

urlpatterns = router.urls
