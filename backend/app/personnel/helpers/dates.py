"""Dates spelled out in Russian and Kazakh (ТЗ §6.3).

Russian uses the genitive month form ("05 августа 2026 года"); Kazakh uses the
nominative month name followed by "жыл" ("05 тамыз 2026 жыл").
"""
from __future__ import annotations

from datetime import date, timedelta

_ONE_DAY = timedelta(days=1)

_RU_MONTHS_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

_KK_MONTHS = {
    1: "қаңтар", 2: "ақпан", 3: "наурыз", 4: "сәуір",
    5: "мамыр", 6: "маусым", 7: "шілде", 8: "тамыз",
    9: "қыркүйек", 10: "қазан", 11: "қараша", 12: "желтоқсан",
}


def date_in_words(d: date, lang: str = "ru") -> str:
    """Format a date with the month spelled out.

    'ru' -> '05 августа 2026 года'; 'kk' -> '05 тамыз 2026 жыл'.
    """
    if lang == "kk":
        return f"{d.day:02d} {_KK_MONTHS[d.month]} {d.year} жыл"
    return f"{d.day:02d} {_RU_MONTHS_GENITIVE[d.month]} {d.year} года"


def date_short(d: date) -> str:
    """'05.08.2026'."""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def add_months(d: date, months: int) -> date:
    """Add `months` to a date, clamping the day to the target month's length
    (31 Jan + 1 month -> 28/29 Feb). Used to compute the probation end date."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # last day of the target month
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - _ONE_DAY).day
    return date(year, month, min(d.day, last_day))
