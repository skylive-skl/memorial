import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.memorials import models as memorial_models
from apps.memorials.models import Memorial
from apps.memorials.short_code import ALPHABET, LENGTH, generate_short_code
from apps.memorials.tests.factories import MemorialFactory


def test_alphabet_has_no_ambiguous_characters():
    assert not set("01oOlIi") & set(ALPHABET)
    assert len(set(ALPHABET)) == len(ALPHABET) == 55


def test_generated_code_format():
    for _ in range(100):
        code = generate_short_code()
        assert len(code) == LENGTH
        assert set(code) <= set(ALPHABET)


pytestmark = pytest.mark.django_db


def test_generated_on_create():
    memorial = MemorialFactory()

    assert len(memorial.short_code) == LENGTH
    assert set(memorial.short_code) <= set(ALPHABET)


def test_unique_across_memorials():
    codes = {MemorialFactory().short_code for _ in range(50)}

    assert len(codes) == 50


def test_retries_on_collision(monkeypatch):
    existing = MemorialFactory()
    codes = iter([existing.short_code, existing.short_code, "NEWCODE2"])
    monkeypatch.setattr(memorial_models, "generate_short_code", lambda: next(codes))

    memorial = MemorialFactory()

    assert memorial.short_code == "NEWCODE2"


def test_retries_on_insert_race(monkeypatch):
    """exists() не увидел конфликт (параллельная вставка) — повтор после IntegrityError."""
    existing = MemorialFactory()
    codes = iter([existing.short_code, "NEWCODE3"])
    monkeypatch.setattr(memorial_models, "generate_short_code", lambda: next(codes))
    real_filter = Memorial.objects.filter
    monkeypatch.setattr(
        Memorial.objects,
        "filter",
        lambda *a, **kw: real_filter(pk=-1) if "short_code" in kw else real_filter(*a, **kw),
    )

    memorial = MemorialFactory()

    assert memorial.short_code == "NEWCODE3"


def test_cannot_be_set_manually_on_create():
    with pytest.raises(ValidationError):
        MemorialFactory(short_code="MANUAL22")


def test_not_regenerated_on_save():
    memorial = MemorialFactory()
    code = memorial.short_code

    memorial.first_name = "Пётр"
    memorial.save()
    memorial.refresh_from_db()

    assert memorial.short_code == code


def test_cannot_be_changed_via_model():
    memorial = MemorialFactory()
    code = memorial.short_code
    memorial.short_code = "CHANGED2"

    with pytest.raises(ValidationError):
        memorial.save()

    assert Memorial.objects.get(pk=memorial.pk).short_code == code


def test_cannot_be_changed_on_instance_not_loaded_from_db():
    memorial = MemorialFactory()
    copy = Memorial(
        **{f.attname: getattr(memorial, f.attname) for f in Memorial._meta.concrete_fields}
    )
    copy._state.adding = False
    copy.short_code = "CHANGED2"

    with pytest.raises(ValidationError):
        copy.save()


def test_cannot_be_changed_via_queryset_update():
    memorial = MemorialFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Memorial.objects.filter(pk=memorial.pk).update(short_code="CHANGED2")

    assert Memorial.objects.get(pk=memorial.pk).short_code == memorial.short_code


def test_other_fields_can_be_updated_via_queryset():
    memorial = MemorialFactory()

    Memorial.objects.filter(pk=memorial.pk).update(
        first_name="Пётр", short_code=memorial.short_code
    )

    assert Memorial.objects.get(pk=memorial.pk).first_name == "Пётр"
