"""Пересчёт оклада «на руки ↔ к начислению» по ставкам 2026 (rates.py).

Клиенты называют сумму на руки, но в документах оклад всегда указывается
к начислению (gross). Здесь — единственный источник формулы; фронтенд её не
дублирует, а вызывает /personnel/salary/convert.

Помесячно: ОПВ 10 % (потолок 50 МЗП), ВОСМС 2 % (потолок 20 МЗП),
ИПН 10 % от (gross − ОПВ − ВОСМС − базовый вычет 30 МРП, если применяется).
Прогрессивная ставка ИПН — годовое понятие (порог 8500 МРП за год) — в помесячном
пересчёте не применяется.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.personnel.rates import RatePeriod, get_rates


def _round_tenge(x: float) -> int:
    """Округление до целого тенге по правилу «половина вверх» (как в расчётных)."""
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class SalaryBreakdown:
    gross: int          # оклад к начислению (идёт в документ)
    net: int            # на руки
    opv: int            # обязательные пенсионные взносы (10 %)
    vosms: int          # взносы ОСМС с работника (2 %)
    ipn: int            # ИПН (10 % после вычетов)
    base_deduction: int  # применённый базовый вычет (30 МРП или 0)
    taxable: int        # облагаемая ИПН база


def net_from_gross(gross: int, apply_base_deduction: bool, rates: RatePeriod) -> SalaryBreakdown:
    """Считает удержания и сумму на руки от оклада к начислению."""
    if gross < 0:
        raise ValueError("Оклад не может быть отрицательным")
    opv = _round_tenge(rates.opv_rate * min(gross, rates.opv_base_cap_mzp * rates.mzp))
    vosms = _round_tenge(rates.vosms_rate * min(gross, rates.vosms_base_cap_mzp * rates.mzp))
    base_deduction = rates.base_deduction_mrp * rates.mrp if apply_base_deduction else 0
    taxable = max(0, gross - opv - vosms - base_deduction)
    ipn = _round_tenge(rates.ipn_rate * taxable)
    net = gross - opv - vosms - ipn
    return SalaryBreakdown(gross=gross, net=net, opv=opv, vosms=vosms,
                           ipn=ipn, base_deduction=base_deduction, taxable=taxable)


def gross_from_net(net_target: int, apply_base_deduction: bool, rates: RatePeriod) -> SalaryBreakdown:
    """Обратный расчёт: подбирает целый оклад к начислению, дающий заданную сумму
    на руки. Бинарный поиск по монотонной функции — устойчив к потолкам и округлению.
    Возвращает разбор для найденного gross (его net может отличаться от цели на
    считанные тенге из-за округления удержаний — это нормально)."""
    if net_target < 0:
        raise ValueError("Сумма на руки не может быть отрицательной")
    if net_target == 0:
        return net_from_gross(0, apply_base_deduction, rates)
    lo, hi = net_target, net_target * 3 + 1_000_000
    while net_from_gross(hi, apply_base_deduction, rates).net < net_target:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if net_from_gross(mid, apply_base_deduction, rates).net < net_target:
            lo = mid + 1
        else:
            hi = mid
    # lo — наименьший gross с net >= цели; сосед снизу может быть ближе
    candidates = [lo] + ([lo - 1] if lo - 1 >= 0 else [])
    best = min(candidates, key=lambda g: abs(net_from_gross(g, apply_base_deduction, rates).net - net_target))
    return net_from_gross(best, apply_base_deduction, rates)


def convert_salary(amount: int, mode: str, apply_base_deduction: bool,
                   on: Optional[date] = None) -> SalaryBreakdown:
    """mode='gross' — amount уже к начислению; mode='net' — amount на руки, ищем gross."""
    rates = get_rates(on)
    if mode == "gross":
        return net_from_gross(amount, apply_base_deduction, rates)
    if mode == "net":
        return gross_from_net(amount, apply_base_deduction, rates)
    raise ValueError(f"Неизвестный режим: {mode!r} (ожидается 'gross' или 'net')")
