"""Tests for ИИН / БИН validation and parsing.

Vectors are hand-computed: first-11-digit weighted sum mod 11 gives the 12th
(control) digit. The IIN's 7th digit encodes century+gender.
"""
from datetime import date

from app.personnel.helpers.iin import (
    is_valid_iin, is_valid_bin, parse_iin, _checksum_ok, _WEIGHTS_1, _WEIGHTS_2,
)

# Hand-verified valid vectors.
VALID_IIN_MALE_1990 = "900715312346"     # 1990-07-15, male
VALID_IIN_FEMALE_2001 = "010308600015"   # 2001-03-08, female
VALID_BIN = "150640001237"


def test_valid_iin_accepted():
    assert is_valid_iin(VALID_IIN_MALE_1990)
    assert is_valid_iin(VALID_IIN_FEMALE_2001)


def test_parse_iin_male_1990():
    info = parse_iin(VALID_IIN_MALE_1990)
    assert info.birth_date == date(1990, 7, 15)
    assert info.gender == "male"


def test_parse_iin_female_2001():
    info = parse_iin(VALID_IIN_FEMALE_2001)
    assert info.birth_date == date(2001, 3, 8)
    assert info.gender == "female"


def test_wrong_check_digit_rejected():
    # Same first 11 digits, last digit flipped from 6 to 0.
    assert not is_valid_iin("900715312340")


def test_wrong_length_rejected():
    assert not is_valid_iin("12345")
    assert not is_valid_iin("9007153123467")  # 13 digits


def test_non_digit_rejected():
    assert not is_valid_iin("90071531234x")
    assert not is_valid_iin("")


def test_impossible_date_rejected_but_gender_parsed():
    # Month 13, checksum-valid: structural checksum passes, date does not.
    iin = "901315312344"
    assert _checksum_ok([int(c) for c in iin])  # checksum itself is fine
    assert not is_valid_iin(iin)                 # ...but the date is impossible
    info = parse_iin(iin)
    assert info.birth_date is None
    assert info.gender == "male"


def test_bad_century_digit_rejected():
    # 7th digit 0 is not a valid century/gender marker.
    # Build a checksum-valid number with 7th digit 0.
    prefix = [9, 0, 0, 7, 1, 5, 0, 1, 2, 3, 4]
    control = sum(d * w for d, w in zip(prefix, _WEIGHTS_1)) % 11
    if control == 10:
        control = sum(d * w for d, w in zip(prefix, _WEIGHTS_2)) % 11
    iin = "".join(str(d) for d in prefix) + str(control)
    assert _checksum_ok([int(c) for c in iin])
    assert parse_iin(iin).gender is None
    assert not is_valid_iin(iin)


def test_second_pass_weights_branch():
    """Find a prefix whose first-pass remainder is 10 and confirm the module
    validates the number completed with the second-pass control digit."""
    for serial in range(0, 100000):
        prefix = [9, 0, 0, 7, 1, 5, 3] + [int(c) for c in f"{serial:04d}"]
        if sum(d * w for d, w in zip(prefix, _WEIGHTS_1)) % 11 != 10:
            continue
        control = sum(d * w for d, w in zip(prefix, _WEIGHTS_2)) % 11
        if control == 10:
            continue  # genuinely invalid; keep searching
        iin = "".join(str(d) for d in prefix) + str(control)
        assert is_valid_iin(iin)
        # A different last digit must be rejected.
        wrong = iin[:-1] + str((control + 1) % 10)
        assert not is_valid_iin(wrong)
        return
    raise AssertionError("no second-pass vector found in search space")


def test_valid_bin_accepted():
    assert is_valid_bin(VALID_BIN)


def test_bin_rejects_bad_checksum_length_nondigit():
    assert not is_valid_bin("150640001230")  # wrong control digit
    assert not is_valid_bin("15064000123")   # 11 digits
    assert not is_valid_bin("15064000123x")


def test_iin_tolerates_separators():
    from app.personnel.helpers.iin import is_valid_iin
    assert is_valid_iin("950313300574")       # чистый
    assert is_valid_iin("950313 300574")      # с пробелом — валидный
    assert is_valid_iin("950313-300574")      # с дефисом — валидный
    assert not is_valid_iin("745820400487")   # месяц 58 — невалиден и с очисткой
