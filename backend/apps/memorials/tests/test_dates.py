import datetime

import pytest
from django.core.exceptions import ValidationError

from apps.memorials.dates import is_before, normalize
from apps.memorials.tests.factories import MemorialFactory

D = datetime.date


class TestNormalize:
    def test_year(self):
        assert normalize(D(1950, 5, 17), "year") == D(1950, 1, 1)

    def test_month(self):
        assert normalize(D(1950, 5, 17), "month") == D(1950, 5, 1)

    def test_day(self):
        assert normalize(D(1950, 5, 17), "day") == D(1950, 5, 17)

    def test_none(self):
        assert normalize(None, "year") is None


@pytest.mark.parametrize(
    ("first", "first_p", "second", "second_p", "expected"),
    [
        (D(1950, 5, 17), "day", D(1950, 5, 18), "day", True),
        (D(1950, 5, 17), "day", D(1950, 5, 17), "day", False),
        # «май 1950» не раньше «1950 года» и наоборот
        (D(1950, 5, 1), "month", D(1950, 1, 1), "year", False),
        (D(1950, 1, 1), "year", D(1950, 5, 1), "month", False),
        (D(1950, 5, 17), "day", D(1950, 5, 1), "month", False),
        (D(1949, 12, 31), "day", D(1950, 1, 1), "year", True),
    ],
)
def test_is_before(first, first_p, second, second_p, expected):
    assert is_before(first, first_p, second, second_p) is expected


pytestmark = pytest.mark.django_db


class TestMemorialDates:
    @pytest.mark.parametrize(
        ("precision", "stored"),
        [("year", D(1950, 1, 1)), ("month", D(1950, 5, 1)), ("day", D(1950, 5, 17))],
    )
    def test_stored_normalized(self, precision, stored):
        memorial = MemorialFactory(birth_date=D(1950, 5, 17), birth_date_precision=precision)

        memorial.refresh_from_db()
        assert memorial.birth_date == stored

    def test_death_before_birth_rejected(self):
        with pytest.raises(ValidationError) as exc:
            MemorialFactory(birth_date=D(1950, 5, 17), death_date=D(1950, 5, 16))

        assert "death_date" in exc.value.message_dict

    def test_same_day_allowed(self):
        MemorialFactory(birth_date=D(1950, 5, 17), death_date=D(1950, 5, 17))

    def test_mixed_precision_same_period_allowed(self):
        memorial = MemorialFactory(
            birth_date=D(1950, 5, 17),
            birth_date_precision="month",
            death_date=D(1950, 3, 2),
            death_date_precision="year",
        )

        assert memorial.birth_date == D(1950, 5, 1)
        assert memorial.death_date == D(1950, 1, 1)

    def test_mixed_precision_earlier_year_rejected(self):
        with pytest.raises(ValidationError):
            MemorialFactory(
                birth_date=D(1950, 5, 17),
                birth_date_precision="month",
                death_date=D(1949, 1, 1),
                death_date_precision="year",
            )

    def test_future_date_rejected(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days=2)

        with pytest.raises(ValidationError) as exc:
            MemorialFactory(death_date=tomorrow)

        assert "death_date" in exc.value.message_dict

    def test_current_year_with_year_precision_allowed(self):
        MemorialFactory(death_date=datetime.date.today(), death_date_precision="year")

    def test_dates_are_optional(self):
        memorial = MemorialFactory(birth_date=None, death_date=None)

        assert memorial.pk

    def test_full_clean_normalizes_and_validates(self):
        memorial = MemorialFactory.build(
            birth_date=D(1950, 5, 17), birth_date_precision="year", death_date=D(1900, 1, 1)
        )

        with pytest.raises(ValidationError) as exc:
            memorial.full_clean()

        assert memorial.birth_date == D(1950, 1, 1)
        assert "death_date" in exc.value.message_dict
