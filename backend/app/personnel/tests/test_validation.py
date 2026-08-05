"""Tests for the hiring-form business-rule validations."""
from datetime import date
from decimal import Decimal

from app.personnel.helpers.validation import (
    validate_salary, validate_probation, validate_dates, validate_iin_matches,
)
from app.personnel.rates import get_rates


def test_salary_below_mzp_warns_at_full_rate():
    on = date(2026, 3, 1)
    mzp = get_rates(on).mzp
    assert validate_salary(Decimal(mzp - 1), rate=1.0, on=on) != []
    assert validate_salary(Decimal(mzp), rate=1.0, on=on) == []
    assert validate_salary(Decimal(mzp + 100000), rate=1.0, on=on) == []


def test_salary_below_mzp_not_warned_at_part_rate():
    on = date(2026, 3, 1)
    mzp = get_rates(on).mzp
    # part-time: below МЗП is lawful, no warning
    assert validate_salary(Decimal(mzp - 1), rate=0.5, on=on) == []
    assert validate_salary(Decimal(mzp // 2), rate=0.75, on=on) == []
    # default rate is full → still warns
    assert validate_salary(Decimal(mzp - 1), on=on) != []


def test_probation_bounds():
    assert validate_probation(0) == []
    assert validate_probation(3) == []
    assert validate_probation(4) != []
    assert validate_probation(-1) != []


def test_start_before_contract_warns():
    assert validate_dates(date(2026, 8, 1), date(2026, 8, 5)) != []
    assert validate_dates(date(2026, 8, 5), date(2026, 8, 5)) == []
    assert validate_dates(date(2026, 8, 10), date(2026, 8, 5)) == []


def test_iin_mismatch_warns():
    # 900715312346 -> 1990-07-15, male
    assert validate_iin_matches("900715312346", date(1990, 7, 15), "male") == []
    assert validate_iin_matches("900715312346", date(1991, 1, 1), "male") != []
    assert validate_iin_matches("900715312346", date(1990, 7, 15), "female") != []
