from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.core.choices import Language
from apps.memorials import dates
from apps.memorials.dates import DatePrecision
from apps.memorials.short_code import LENGTH as SHORT_CODE_LENGTH
from apps.memorials.short_code import generate_short_code

SHORT_CODE_ATTEMPTS = 10
DESCRIPTION_MAX_LENGTH = 10_000


class Memorial(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memorials"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    birth_date_precision = models.CharField(
        max_length=5, choices=DatePrecision.choices, default=DatePrecision.DAY
    )
    death_date = models.DateField(null=True, blank=True)
    death_date_precision = models.CharField(
        max_length=5, choices=DatePrecision.choices, default=DatePrecision.DAY
    )
    description = models.TextField(
        blank=True, validators=[MaxLengthValidator(DESCRIPTION_MAX_LENGTH)]
    )
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.RU)
    theme = models.ForeignKey("themes.Theme", on_delete=models.PROTECT, related_name="memorials")
    theme_overrides = models.JSONField(default=dict, blank=True)
    # Генерируется один раз и никогда не меняется: QR выгравирован на камне.
    # Защита: save() + триггер в БД (миграция 0002) + read-only в сериализаторах.
    short_code = models.CharField(max_length=SHORT_CODE_LENGTH, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (models.Index(fields=("owner", "-created_at")),)

    def __str__(self) -> str:
        return f"{self.last_name} {self.first_name} ({self.short_code})"

    def save(self, *args, **kwargs) -> None:
        self.normalize_dates()
        self.validate_dates()
        if self._state.adding:
            self._insert_with_short_code(*args, **kwargs)
        else:
            self._check_short_code_unchanged()
            super().save(*args, **kwargs)
        self._loaded_short_code = self.short_code

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_short_code = instance.short_code
        return instance

    def clean(self) -> None:
        super().clean()
        self.normalize_dates()
        self.validate_dates()

    def normalize_dates(self) -> None:
        """Приводит даты к виду по точности (год → YYYY-01-01, месяц → YYYY-MM-01)."""
        for field in ("birth_date", "death_date"):
            # to_python: как и сам Django, принимаем дату строкой "YYYY-MM-DD".
            value = self._meta.get_field(field).to_python(getattr(self, field))
            setattr(self, field, dates.normalize(value, getattr(self, f"{field}_precision")))

    def validate_dates(self) -> None:
        errors: dict[str, str] = {}
        today = timezone.localdate()
        for field in ("birth_date", "death_date"):
            value = getattr(self, field)
            precision = getattr(self, f"{field}_precision")
            if value is not None and dates.is_before(today, DatePrecision.DAY, value, precision):
                errors[field] = "Date cannot be in the future."
        if (
            "death_date" not in errors
            and self.birth_date is not None
            and self.death_date is not None
            and dates.is_before(
                self.death_date,
                self.death_date_precision,
                self.birth_date,
                self.birth_date_precision,
            )
        ):
            errors["death_date"] = "Death date cannot be earlier than birth date."
        if errors:
            raise ValidationError(errors)

    def publish(self) -> None:
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=("status", "published_at", "updated_at"))

    def unpublish(self) -> None:
        self.status = self.Status.DRAFT
        self.save(update_fields=("status", "updated_at"))

    def _insert_with_short_code(self, *args, **kwargs) -> None:
        if self.short_code:
            raise ValidationError({"short_code": "short_code is generated automatically."})
        for _ in range(SHORT_CODE_ATTEMPTS):
            code = generate_short_code()
            if Memorial.objects.filter(short_code=code).exists():
                continue
            self.short_code = code
            try:
                # Гонка между exists() и INSERT: повторяем с новым кодом.
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError as exc:
                if not _is_short_code_conflict(exc):
                    raise
                self.short_code = ""
        raise RuntimeError("Could not generate a unique short_code")

    def _check_short_code_unchanged(self) -> None:
        loaded = getattr(self, "_loaded_short_code", None)
        if loaded is None:
            loaded = (
                Memorial.objects.filter(pk=self.pk).values_list("short_code", flat=True).first()
            )
        if loaded is not None and loaded != self.short_code:
            raise ValidationError({"short_code": "short_code cannot be changed."})


def _is_short_code_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    constraint = getattr(diag, "constraint_name", "") or ""
    return "short_code" in constraint
