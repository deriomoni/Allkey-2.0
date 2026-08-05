"""Business-rule validations for the hiring form (ТЗ §6).

These return a list of human-readable warnings (in Russian) rather than raising,
so the form can show them inline; the caller decides which are hard blocks
(invalid ИИН/БИН) and which are soft warnings (oklad below МЗП).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.personnel.helpers.iin import parse_iin
from app.personnel.rates import get_rates


def validate_salary(oklad: Decimal, on: Optional[date] = None) -> List[str]:
    """Warn if the salary is below the minimum wage in force."""
    warnings: List[str] = []
    rates = get_rates(on or (date.today() if on is None else on))
    if oklad < rates.mzp:
        warnings.append(
            f"Оклад {oklad} ₸ ниже МЗП ({rates.mzp} ₸). Проверьте условия оплаты."
        )
    return warnings


def validate_probation(months: int) -> List[str]:
    """Probation must not exceed 3 months (ст. 36 ТК РК)."""
    warnings: List[str] = []
    if months < 0:
        warnings.append("Испытательный срок не может быть отрицательным.")
    if months > 3:
        warnings.append("Испытательный срок не может превышать 3 месяца (ст. 36 ТК РК).")
    return warnings


def validate_dates(start_date: date, contract_date: date) -> List[str]:
    """Start of work must not precede the contract date."""
    warnings: List[str] = []
    if start_date < contract_date:
        warnings.append("Дата начала работы раньше даты трудового договора.")
    return warnings


def validate_iin_matches(iin: str, birth_date: Optional[date], gender: Optional[str]) -> List[str]:
    """Cross-check the birth date / gender entered in the form against the IIN."""
    warnings: List[str] = []
    info = parse_iin(iin)
    if info is None:
        return warnings  # structural validity handled by is_valid_iin elsewhere
    if birth_date is not None and info.birth_date is not None and info.birth_date != birth_date:
        warnings.append(
            f"Дата рождения из ИИН ({info.birth_date.isoformat()}) не совпадает с введённой "
            f"({birth_date.isoformat()})."
        )
    if gender is not None and info.gender is not None and info.gender != gender:
        warnings.append("Пол из ИИН не совпадает с введённым.")
    return warnings
