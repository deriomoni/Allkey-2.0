"""Dates spelled out in Russian and Kazakh (ТЗ §6.3).

Russian uses the genitive month form ("05 августа 2026 года"); Kazakh uses the
nominative month name followed by "жыл" ("05 тамыз 2026 жыл").
"""
from __future__ import annotations

from datetime import date

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
