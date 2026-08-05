"""Validation and parsing of Kazakhstan IIN (ЖСН) and BIN (БСН).

Both IIN (individuals) and BIN (legal entities) are 12-digit identifiers that
share the same control-digit algorithm. The IIN additionally encodes the date
of birth and gender in its first seven digits, which we parse out so the form
can cross-check the manually entered birth date (ТЗ §6.4).

Public API:
    is_valid_iin(value) -> bool
    is_valid_bin(value) -> bool
    parse_iin(value)    -> IinInfo | None   (birth_date + gender)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

# Control-digit weights. First pass; if the remainder is 10 we retry with the
# shifted weights, and if that is also 10 the identifier is invalid.
_WEIGHTS_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
_WEIGHTS_2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]

# 7th digit -> (century, gender). 1/2 = 1800s, 3/4 = 1900s, 5/6 = 2000s;
# odd = male, even = female. Values 0, 7, 8, 9 are invalid.
_CENTURY = {1: 1800, 2: 1800, 3: 1900, 4: 1900, 5: 2000, 6: 2000}
_GENDER = {1: "male", 2: "female", 3: "male", 4: "female", 5: "male", 6: "female"}


def _to_digits(value: str) -> Optional[List[int]]:
    """Return the 12 digits, or None if the value is not exactly 12 digits."""
    cleaned = (value or "").strip()
    if len(cleaned) != 12 or not cleaned.isdigit():
        return None
    return [int(ch) for ch in cleaned]


def _checksum_ok(digits: List[int]) -> bool:
    control = sum(d * w for d, w in zip(digits[:11], _WEIGHTS_1)) % 11
    if control == 10:
        control = sum(d * w for d, w in zip(digits[:11], _WEIGHTS_2)) % 11
        if control == 10:
            return False
    return control == digits[11]


@dataclass
class IinInfo:
    """Data decoded from the first seven digits of an IIN."""
    birth_date: Optional[date]
    gender: Optional[str]  # "male" | "female"


def parse_iin(value: str) -> Optional[IinInfo]:
    """Decode birth date and gender from an IIN.

    Returns None for a structurally invalid string (wrong length / non-digit).
    A well-formed IIN with an impossible date yields IinInfo(birth_date=None, ...)
    so the caller can still read the gender.
    """
    digits = _to_digits(value)
    if digits is None:
        return None

    yy = digits[0] * 10 + digits[1]
    mm = digits[2] * 10 + digits[3]
    dd = digits[4] * 10 + digits[5]
    century_digit = digits[6]

    gender = _GENDER.get(century_digit)
    century = _CENTURY.get(century_digit)

    birth: Optional[date] = None
    if century is not None:
        try:
            birth = date(century + yy, mm, dd)
        except ValueError:
            birth = None

    return IinInfo(birth_date=birth, gender=gender)


def is_valid_iin(value: str) -> bool:
    """True if `value` is a valid IIN: 12 digits, correct checksum, decodable
    century/gender digit and a real calendar birth date."""
    digits = _to_digits(value)
    if digits is None or not _checksum_ok(digits):
        return False
    info = parse_iin(value)
    return info is not None and info.gender is not None and info.birth_date is not None


def is_valid_bin(value: str) -> bool:
    """True if `value` is a valid BIN: 12 digits with a correct checksum.

    Unlike the IIN, the BIN does not encode a birth date, so only length and the
    control digit are checked.
    """
    digits = _to_digits(value)
    return digits is not None and _checksum_ok(digits)
