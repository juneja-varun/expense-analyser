from django.apps import AppConfig


class CategoriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.categories"

    # Seeding a new household is handled by apps.rules.signals, which can see
    # both categories and rules and so can guarantee the tree exists before
    # rules try to resolve it by path.
