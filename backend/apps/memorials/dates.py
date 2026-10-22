"""Даты с точностью: day | month | year.

При точности `year` хранится YYYY-01-01, при `month` — YYYY-MM-01.
"""

import datetime

from django.db import models


class DatePrecision(models.TextChoices):
    DAY = "day", "Day"
    MONTH = "month", "Month"
    YEAR = "year", "Year"


# Чем больше, тем грубее.
_COARSENESS = {DatePrecision.DAY: 0, DatePrecision.MONTH: 1, DatePrecision.YEAR: 2}


def normalize(value: datetime.date | None, precision: str) -> datetime.date | None:
    if value is None:
        return None
    if precision == DatePrecision.YEAR:
        return value.replace(month=1, day=1)
    if precision == DatePrecision.MONTH:
        return value.replace(day=1)
    return value


def coarser(a: str, b: str) -> str:
    return a if _COARSENESS[DatePrecision(a)] >= _COARSENESS[DatePrecision(b)] else b


def is_before(
    first: datetime.date, first_precision: str, second: datetime.date, second_precision: str
) -> bool:
    """`first` строго раньше `second` с учётом точности обеих дат.

    Сравниваем по более грубой точности: «май 1950» не раньше «1950 года».
    """
    precision = coarser(first_precision, second_precision)
    return normalize(first, precision) < normalize(second, precision)
