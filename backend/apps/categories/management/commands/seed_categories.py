"""Seed the default category tree for households that lack it.

    python manage.py seed_categories            # every household
    python manage.py seed_categories --household 3

Idempotent, so it is also the way to backfill categories added to the taxonomy
in a later release.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Household
from apps.categories.services import seed_default_categories


class Command(BaseCommand):
    help = "Create the default category tree for households that don't have it"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--household", type=int, help="Only this household ID")

    def handle(self, *args: Any, **options: Any) -> None:
        households = Household.objects.all()
        if options.get("household"):
            households = households.filter(pk=options["household"])
            if not households.exists():
                raise CommandError(f"No household with ID {options['household']}")

        total = 0
        for household in households:
            created = seed_default_categories(household)
            total += created
            state = f"{created} created" if created else "already seeded"
            self.stdout.write(f"  {household.name} (#{household.pk}): {state}")

        self.stdout.write(self.style.SUCCESS(f"{total} categor(ies) created"))
