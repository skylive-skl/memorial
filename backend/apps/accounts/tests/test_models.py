import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email():
    user = User.objects.create_user(" Foo@Example.COM ", "Str0ng-pass-123")

    assert user.email == "foo@example.com"
    assert not user.is_staff


def test_create_superuser():
    user = User.objects.create_superuser("admin@example.com", "Str0ng-pass-123")

    assert user.is_staff and user.is_superuser


def test_email_lookup_is_case_insensitive():
    User.objects.create_user("foo@example.com", "Str0ng-pass-123")

    assert User.objects.get_by_natural_key("FOO@example.com").email == "foo@example.com"
