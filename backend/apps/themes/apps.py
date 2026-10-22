from django.apps import AppConfig


class ThemesConfig(AppConfig):
    name = "apps.themes"

    def ready(self) -> None:
        from apps.themes import signals  # noqa: F401
