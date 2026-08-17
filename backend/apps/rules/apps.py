from django.apps import AppConfig


class RulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rules"

    def ready(self) -> None:
        # Imported for its side effect: registers the household post_save
        # receiver that seeds the category tree and the bundled merchant rules.
        from apps.rules import signals  # noqa: F401
