from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Household

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Household, dispatch_uid="bootstrap_new_household")
def bootstrap_new_household(sender, instance: Household, created: bool, **kwargs) -> None:
    """Give a new household its category tree and the bundled merchant rules.

    Both steps live in one receiver, in this app, for two reasons:

    * **Order matters.** Rules resolve categories by path, so the tree has to
      exist first. Sequential code in one receiver guarantees that; two
      receivers would depend on app registration order, which is a fragile
      thing to rely on.
    * **Layering.** `rules` already depends on `categories`, so this is the
      layer that can see both. Putting it in `categories` would invert that.

    Neither step may fail registration: a household with no categories or no
    rules is recoverable (`manage.py seed_categories`, `manage.py seed_rules`),
    an account that could not be created is not.
    """
    if not created:
        return

    from apps.categories.services import seed_default_categories
    from apps.rules.builtin import seed_builtin_rules

    try:
        seed_default_categories(instance)
    except Exception:
        logger.exception("Could not seed categories for household %s", instance.pk)
        return

    try:
        seed_builtin_rules(instance)
    except Exception:
        logger.exception("Could not seed builtin rules for household %s", instance.pk)
