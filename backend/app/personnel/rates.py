"""Payroll rates and tax constants with an effective-date window (ТЗ §7).

Every constant that changes year to year lives here, not hard-coded in formulas,
so moving to 2027 is a data edit — add a new RatePeriod — not a code change.
These feed both the form validations (МЗП floor, etc.) and the future
"на руки ↔ грязными" calculator.

All monetary values are in tenge; rates are fractions (0.10 == 10%). Caps are
expressed as a multiple of МЗП where the law defines them that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RatePeriod:
    effective_from: date
    effective_to: Optional[date]  # None == open-ended

    mrp: int  # месячный расчётный показатель
    mzp: int  # минимальная заработная плата

    ipn_rate: float                 # ИПН, базовая ставка
    ipn_progressive_from_mrp: int   # порог годового дохода (в МРП) для повышенной ставки
    ipn_progressive_rate: float     # ставка сверх порога
    base_deduction_mrp: int         # базовый налоговый вычет, МРП/мес
    base_deduction_year_cap_mrp: int  # годовой потолок базового вычета, МРП

    opv_rate: float                 # обязательные пенсионные взносы
    opv_base_cap_mzp: int           # потолок базы ОПВ, кратно МЗП
    opvr_rate: float                # обязательные пенсионные взносы работодателя
    opvr_base_min_mzp: int
    opvr_base_cap_mzp: int
    so_rate: float                  # социальные отчисления
    vosms_rate: float               # взносы ОСМС (с работника)
    vosms_base_cap_mzp: int
    oosms_rate: float               # отчисления ОСМС (работодатель)
    oosms_base_cap_mzp: int
    sn_rate: float                  # социальный налог (ТОО на ОУР)
    unified_payment_rate: float     # единый платёж с ФОТ


# Newest period first is not required; get_rates scans the whole list.
RATE_PERIODS = [
    RatePeriod(
        effective_from=date(2026, 1, 1),
        effective_to=None,
        mrp=4325,
        mzp=85000,
        ipn_rate=0.10,
        ipn_progressive_from_mrp=8500,
        ipn_progressive_rate=0.15,
        base_deduction_mrp=30,
        base_deduction_year_cap_mrp=360,
        opv_rate=0.10,
        opv_base_cap_mzp=50,
        opvr_rate=0.035,
        opvr_base_min_mzp=1,
        opvr_base_cap_mzp=50,
        so_rate=0.05,
        vosms_rate=0.02,
        vosms_base_cap_mzp=20,
        oosms_rate=0.03,
        oosms_base_cap_mzp=40,
        sn_rate=0.06,
        unified_payment_rate=0.248,
    ),
]


def get_rates(on: Optional[date] = None) -> RatePeriod:
    """Return the RatePeriod in force on `on` (defaults to the latest period).

    Raises LookupError if no period covers the date, so a missing 2027 config
    fails loudly instead of silently applying stale 2026 numbers.
    """
    if on is None:
        return max(RATE_PERIODS, key=lambda p: p.effective_from)
    for period in RATE_PERIODS:
        if period.effective_from <= on and (period.effective_to is None or on <= period.effective_to):
            return period
    raise LookupError(f"Нет конфигурации ставок на дату {on.isoformat()}")
