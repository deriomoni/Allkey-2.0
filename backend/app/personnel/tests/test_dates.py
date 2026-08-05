"""Tests for date-to-words in Russian and Kazakh."""
from datetime import date

from app.personnel.helpers.dates import date_in_words


def test_ru_date():
    assert date_in_words(date(2026, 8, 5), lang="ru") == "05 августа 2026 года"


def test_kk_date():
    assert date_in_words(date(2026, 8, 5), lang="kk") == "05 тамыз 2026 жыл"


def test_ru_all_months_have_genitive_form():
    for m in range(1, 13):
        out = date_in_words(date(2026, m, 1), lang="ru")
        assert out.endswith("2026 года")


def test_kk_january_and_december():
    assert date_in_words(date(2026, 1, 1), lang="kk") == "01 қаңтар 2026 жыл"
    assert date_in_words(date(2026, 12, 31), lang="kk") == "31 желтоқсан 2026 жыл"
