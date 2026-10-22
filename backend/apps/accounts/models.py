from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Кастомный пользователь. Логин по email и остальные поля — задача 1.1."""
