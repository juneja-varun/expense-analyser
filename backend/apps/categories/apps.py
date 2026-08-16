from django.apps import AppConfig


class CategoriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.categories"

    def ready(self) -> None:
        # Imported for its side effect: registers the household post_save
        # receiver that seeds the default category tree.
        from apps.categories import signals  # noqa: F401
