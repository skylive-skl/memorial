from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"

    def ready(self) -> None:
        # Регистрирует OpenAPI-описание cookie-аутентификации для drf-spectacular.
        from apps.accounts import authentication  # noqa: F401
