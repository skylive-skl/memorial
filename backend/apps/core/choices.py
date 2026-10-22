from django.db import models


class Language(models.TextChoices):
    """Языки интерфейса: кабинет (User.preferred_language) и публичная страница."""

    RU = "ru", "Русский"
    UZ = "uz", "Oʻzbekcha"
    EN = "en", "English"
