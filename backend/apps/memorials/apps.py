from django.apps import AppConfig


class MemorialsConfig(AppConfig):
    name = "apps.memorials"

    def ready(self) -> None:
        from pillow_heif import register_heif_opener

        from apps.memorials import signals  # noqa: F401

        register_heif_opener()  # Pillow открывает HEIC/HEIF (фото с iPhone)
