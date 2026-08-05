"""Tests for number-to-words (Kazakh fully custom) and the currency wrapper."""
from app.personnel.helpers.numbers import (
    kk_int_to_words, amount_in_words, _split_amount,
)


def test_kk_zero_and_units():
    assert kk_int_to_words(0) == "нөл"
    assert kk_int_to_words(1) == "бір"
    assert kk_int_to_words(5) == "бес"
    assert kk_int_to_words(9) == "тоғыз"


def test_kk_tens():
    assert kk_int_to_words(10) == "он"
    assert kk_int_to_words(11) == "он бір"
    assert kk_int_to_words(20) == "жиырма"
    assert kk_int_to_words(21) == "жиырма бір"
    assert kk_int_to_words(90) == "тоқсан"
    assert kk_int_to_words(99) == "тоқсан тоғыз"


def test_kk_hundreds():
    assert kk_int_to_words(100) == "жүз"          # not 'бір жүз'
    assert kk_int_to_words(101) == "жүз бір"
    assert kk_int_to_words(200) == "екі жүз"
    assert kk_int_to_words(345) == "үш жүз қырық бес"


def test_kk_thousands():
    assert kk_int_to_words(1000) == "бір мың"
    assert kk_int_to_words(2000) == "екі мың"
    assert kk_int_to_words(1234) == "бір мың екі жүз отыз төрт"
    assert kk_int_to_words(300000) == "үш жүз мың"


def test_kk_millions():
    assert kk_int_to_words(1000000) == "бір миллион"
    assert kk_int_to_words(2000005) == "екі миллион бес"


def test_kk_negative():
    assert kk_int_to_words(-5) == "минус бес"


def test_split_amount_rounding():
    assert _split_amount(300000) == (300000, 0)
    assert _split_amount("300000.50") == (300000, 50)
    assert _split_amount("0.005") == (0, 1)   # half-up


def test_amount_in_words_kk():
    assert amount_in_words(300000, lang="kk") == "Үш жүз мың теңге 00 тиын"
    assert amount_in_words("300000.50", lang="kk") == "Үш жүз мың теңге 50 тиын"


def test_amount_in_words_ru():
    # num2words(85000, 'ru') == 'восемьдесят пять тысяч'
    assert amount_in_words(85000, lang="ru") == "Восемьдесят пять тысяч тенге 00 тиын"


def test_amount_no_capitalize():
    assert amount_in_words(1, lang="kk", capitalize=False) == "бір теңге 00 тиын"
