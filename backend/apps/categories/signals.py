from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Household

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Household, dispatch_uid="seed_categories_for_new_household")
def seed_categories_for_new_household(sender, instance: Household, created: bool, **kwargs) -> None:
    """Give every new household the default category tree.

    A signal rather than a call inside `UserManager._create_user` for two
    reasons: it avoids an import cycle between accounts and categories, and it
    covers every path that creates a household, not just registration.

    Seeding failures must not fail registration — a household with no
    categories is recoverable (`manage.py seed_categories`), an account that
    couldn't be created is not.
    """
    if not created:
        return

    from apps.categories.services import seed_default_categories

    try:
        seed_default_categories(instance)
    except Exception:
        logger.exception("Could not seed categories for household %s", instance.pk)
