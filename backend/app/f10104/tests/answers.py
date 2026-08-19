"""Построители ответов визарда для тестов движка.

Ключи — идентификаторы вопросов из ТЗ §4 (`docs/tax/101-04/tz-pomogayki.md`),
ровно как в модели данных §9: `answers: {questionId: value}`.

Словарь значений взят из ТЗ и из прототипа `docs/prototypes/pomogayka-101-04.html`,
ничего не придумано:

* **S2.3 (страна)** — ISO alpha-2 для обычных стран либо `OFF<номер>` для
  юрисдикций из перечня № 492. Так сделано в прототипе (`COUNTRIES` +
  `OFFSHORE.map(o => 'OFF' + o.no)`): у офшорных записей ISO-кода нет, а в
  графе D по R-FORM-01 всё равно идёт порядковый номер, а не ISO.
* **S5.5 (вид услуги)** — `id` из раздела `service_kinds` справочника.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# ── S2.1 «Что произошло» ────────────────────────────────────────────────────
PAYMENT = "payment"                     # перечислили деньги
ACT_NO_PAYMENT = "act_no_payment"       # акт подписан, оплаты нет
OFFSET = "offset"                       # взаимозачёт
ADVANCE = "advance"                     # аванс (предоплата)
ACCRUED_DEDUCTED = "accrued_deducted"   # начислено, не выплачено, на вычеты

# ── S2.2 «Кто получатель» ───────────────────────────────────────────────────
LEGAL_ENTITY = "legal_entity"
INDIVIDUAL = "individual"
BRANCH_KZ = "branch_kz"

# ── S5.1 «Тип дохода» ───────────────────────────────────────────────────────
GOODS = "goods"
SERVICES = "services"
ROYALTY = "royalty"
DIVIDENDS = "dividends"
INTEREST = "interest"
RENT = "rent"
TRANSPORT_INTL = "transport_intl"
INSURANCE = "insurance"
CAPITAL_GAIN = "capital_gain"
PENALTY = "penalty"

# ── S6.1 «Место оказания» ───────────────────────────────────────────────────
IN_KZ = "kz"
OUTSIDE_KZ = "outside"
PARTLY = "partly"


def base(**over: Any) -> dict:
    """Минимальный валидный набор ответов. Каждый тест переопределяет своё.

    По умолчанию: ТОО-резидент на НДС, III квартал 2026, платёж юрлицу-нерезиденту,
    услуги, конвенцию не применяем.
    """
    answers = {
        "S1.1": {"quarter": 3, "year": 2026},
        "S1.2": "small",
        "S1.3": "yes",
        "S1.4": "yes",
        "S1.5": "EUR",
        "S2.1": PAYMENT,
        "S2.2": LEGAL_ENTITY,
        "S2.3": "DE",
        "S2.4": {"name": "Nonresident GmbH", "tin": "DE123456789",
                 "contract_no": "1", "contract_date": "2026-07-01"},
        "S2.5": None,
        "S3.1": "no",
        "S3.4": "na",
        "S4.1": date(2026, 7, 10),
        "S4.2": date(2026, 7, 20),
        "S4.4": 1000.0,
        "S4.5": 500.0,
        "S5.1": SERVICES,
        "S5.5": "consulting",
        "S6.1": OUTSIDE_KZ,
        "S7.2": "no",
        "S7.3": "no",
        "S7.4": "no",
        "S7.6": "no",
        "S10": None,
    }
    answers.update(over)
    return answers


def with_convention(**over: Any) -> dict:
    """Ответы с выполненными условиями ст. 705: сертификат есть, доход с ПУ
    не связан, conduit нет, нерезидент — окончательный получатель."""
    return base(**{
        "S7.2": "yes",
        "S7.3": "yes",
        "S7.4": "no",
        "S7.5": "yes",
        "S7.6": "no",
        **over,
    })
