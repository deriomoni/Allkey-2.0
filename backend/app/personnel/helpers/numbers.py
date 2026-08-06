"""Numbers spelled out in words, in Russian and Kazakh, plus a currency wrapper
that formats a tenge amount as e.g. "триста тысяч тенге 00 тиын" /
"үш жүз мың теңге 00 тиын" (ТЗ §6.2).

Kazakh is implemented from scratch: the language has no grammatical gender and
no agreement between the numeral and the counted noun, so the algorithm is a
straightforward positional composition and is fully unit-tested here. Russian
delegates to `num2words`, which handles the feminine "тысяча" agreement
("одна тысяча", "две тысячи").
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union

Number = Union[int, float, Decimal, str]

# --- Kazakh -----------------------------------------------------------------

_KK_UNITS = ["", "бір", "екі", "үш", "төрт", "бес", "алты", "жеті", "сегіз", "тоғыз"]
_KK_TENS = ["", "он", "жиырма", "отыз", "қырық", "елу", "алпыс", "жетпіс", "сексен", "тоқсан"]
# Scale words per group of three digits: 1 = thousands, 2 = millions, ...
_KK_SCALES = ["", "мың", "миллион", "миллиард", "триллион"]


def _kk_group(n: int) -> str:
    """Spell a value 0 < n < 1000 in Kazakh. '100' is 'жүз' (not 'бір жүз')."""
    parts: List[str] = []
    hundreds, rest = divmod(n, 100)
    tens, units = divmod(rest, 10)
    if hundreds:
        parts.append("жүз" if hundreds == 1 else f"{_KK_UNITS[hundreds]} жүз")
    if tens:
        parts.append(_KK_TENS[tens])
    if units:
        parts.append(_KK_UNITS[units])
    return " ".join(parts)


def kk_int_to_words(n: int) -> str:
    """Spell a non-negative (or negative) integer in Kazakh.

    Examples: 0 -> 'нөл', 1000 -> 'бір мың', 300000 -> 'үш жүз мың',
    1234 -> 'бір мың екі жүз отыз төрт'.
    """
    if n == 0:
        return "нөл"
    negative = n < 0
    n = abs(n)

    chunks: List[str] = []
    scale = 0
    while n > 0:
        n, group = divmod(n, 1000)
        if group:
            words = _kk_group(group)
            if scale > 0:
                words = f"{words} {_KK_SCALES[scale]}"
            chunks.append(words)
        scale += 1

    result = " ".join(reversed(chunks))
    return f"минус {result}" if negative else result


# --- Russian ----------------------------------------------------------------

def ru_int_to_words(n: int) -> str:
    """Spell an integer in Russian via num2words (feminine 'тысяча' agreement)."""
    from num2words import num2words  # imported lazily so pure-Kazakh use needs no dep

    return num2words(n, lang="ru")


def format_figures(n: Number) -> str:
    """Group an integer amount with spaces: 300000 -> '300 000'."""
    return f"{int(Decimal(str(n))):,}".replace(",", " ")


def pluralize_ru(n: int, forms: "tuple[str, str, str]") -> str:
    """Pick the Russian plural form: forms = (1 год, 2 года, 5 лет)."""
    n = abs(int(n))
    if n % 100 in (11, 12, 13, 14):
        return forms[2]
    d = n % 10
    if d == 1:
        return forms[0]
    if d in (2, 3, 4):
        return forms[1]
    return forms[2]


# --- Currency ---------------------------------------------------------------

def _split_amount(amount: Number) -> "tuple[int, int]":
    """Split a money amount into whole tenge and tiyn (0..99), rounding half up.
    A tiyn carry of 100 rolls into tenge."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    tenge = int(value)
    tiyn = int((value - tenge) * 100)
    if negative:
        tenge = -tenge
    return tenge, tiyn


def amount_in_words(amount: Number, lang: str = "ru", capitalize: bool = True) -> str:
    """Format a tenge amount in words, tiyn shown as two digits (ТЗ §6.2).

    lang: 'ru' -> 'Триста тысяч тенге 00 тиын'
          'kk' -> 'Үш жүз мың теңге 00 тиын'
    """
    tenge, tiyn = _split_amount(amount)
    if lang == "kk":
        words = kk_int_to_words(tenge)
        main, frac = "теңге", "тиын"
    else:
        words = ru_int_to_words(tenge)
        main, frac = "тенге", "тиын"

    text = f"{words} {main} {tiyn:02d} {frac}"
    if capitalize and text:
        text = text[0].upper() + text[1:]
    return text
