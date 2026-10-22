from typing import ClassVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.choices import Language


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields) -> "User":
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email: str) -> "User":
        return self.get(email=normalize_email(email))


def normalize_email(email: str) -> str:
    """Email храним и ищем в нижнем регистре целиком: Foo@Mail.ru и foo@mail.ru — один аккаунт."""
    return email.strip().lower()


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    preferred_language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.RU
    )
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email
