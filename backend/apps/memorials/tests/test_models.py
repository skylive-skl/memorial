import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from apps.memorials.models import DESCRIPTION_MAX_LENGTH, Memorial
from apps.memorials.tests.factories import MemorialFactory

pytestmark = pytest.mark.django_db


def test_defaults():
    memorial = MemorialFactory()

    assert memorial.status == Memorial.Status.DRAFT
    assert memorial.published_at is None
    assert memorial.language == "ru"
    assert memorial.theme_overrides == {}


def test_publish_and_unpublish():
    memorial = MemorialFactory()

    memorial.publish()
    memorial.refresh_from_db()
    assert memorial.status == Memorial.Status.PUBLISHED
    assert memorial.published_at is not None

    memorial.unpublish()
    memorial.refresh_from_db()
    assert memorial.status == Memorial.Status.DRAFT


def test_description_max_length():
    memorial = MemorialFactory.build(description="x" * (DESCRIPTION_MAX_LENGTH + 1))
    memorial.theme.save()
    memorial.owner.save()

    with pytest.raises(ValidationError) as exc:
        memorial.full_clean()

    assert "description" in exc.value.message_dict


def test_theme_in_use_cannot_be_deleted():
    memorial = MemorialFactory()

    with pytest.raises(ProtectedError):
        memorial.theme.delete()


def test_switching_theme_keeps_data():
    memorial = MemorialFactory(description="Текст")
    other = MemorialFactory().theme

    memorial.theme = other
    memorial.save()
    memorial.refresh_from_db()

    assert memorial.theme == other
    assert memorial.description == "Текст"
