"""Create the bundled merchant rules for households that lack them.

    python manage.py seed_rules            # every household
    python manage.py seed_rules --household 3

Idempotent, so this is also how to backfill merchants added to
builtin_patterns.yaml in a later release. Rules a user has edited or
deactivated are left exactly as they left them.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Household
from apps.rules.builtin import seed_builtin_rules


class Command(BaseCommand):
    help = "Create the bundled merchant categorisation rules"

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
            created = seed_builtin_rules(household)
            total += created
            state = f"{created} created" if created else "already seeded"
            self.stdout.write(f"  {household.name} (#{household.pk}): {state}")

        self.stdout.write(self.style.SUCCESS(f"{total} rule(s) created"))
