"""Золотой эталон: три кейса из официального разбора построчного заполнения
формы 101.04 за I квартал 2026 (С. Зуева, Г. Умрихина, ИС «Параграф»).

Сходимость **до тенге** — условие приёмки движка. Если эти три теста красные,
остальное не имеет значения.

Тесты писались до реализации движка.
"""
from datetime import date

from app.f10104.rules import get_rules

from .answers import base, DIVIDENDS, RENT, TRANSPORT_INTL, OUTSIDE_KZ

Q1_2026 = {"quarter": 1, "year": 2026}


def run(answers: dict, on: date = date(2026, 3, 31)):
    from app.f10104.engine import evaluate  # noqa: PLC0415 — см. комментарий выше

    return evaluate(answers, refbooks=get_rules(), as_of_date=on)


# ── 1. Черногория (офшор № 54), аренда транспортных средств ────────────────

def test_golden_montenegro_vehicle_rent():
    """4 000 EUR × 594,50 = 2 378 000 ₸ · КПН 20 % = 475 600 ₸ · код 1040 ·
    графа D = 54 (порядковый номер, не ISO) · НДС не возникает."""
    v = run(base(
        **{
            "S1.1": Q1_2026,
            "S1.5": "EUR",
            "S2.3": "OFF54",              # Черногория из перечня № 492
            "S5.1": RENT,
            "S5.5": "rent_vehicle",
            "S6.1": OUTSIDE_KZ,
            "S4.1": date(2026, 2, 10),
            "S4.2": date(2026, 2, 20),
            "S4.4": 4000.0,
            "S4.5": 594.50,
        }
    ))

    assert v.kpn.taxable is True
    assert v.kpn.base_kzt == 2_378_000
    assert v.kpn.rate == 0.20
    assert v.kpn.amount_kzt == 475_600
    assert v.kpn.convention_applied is False   # ст. 682 п. 2 — конвенция не применяется
    assert v.graphs["D"] == "54"               # R-FORM-01: номер, а не ISO «ME»
    assert v.graphs["F"] == "1040"
    assert v.vat.applicable is False
    assert "F-OFFSHORE" in v.flags


# ── 2. Нидерланды, международная перевозка, сертификата нет ────────────────

def test_golden_netherlands_intl_transport_no_certificate():
    """7 000 EUR × 591,00 = 4 137 000 ₸ · КПН 5 % = 206 850 ₸ · код 1170 ·
    НДС не возникает (R-VAT-10)."""
    v = run(base(
        **{
            "S1.1": Q1_2026,
            "S1.5": "EUR",
            "S2.3": "NL",
            "S5.1": TRANSPORT_INTL,
            "S7.2": "yes",
            "S7.3": "no",                 # сертификат не получен
            "S4.1": date(2026, 2, 5),
            "S4.2": date(2026, 2, 15),
            "S4.4": 7000.0,
            "S4.5": 591.00,
        }
    ))

    assert v.kpn.taxable is True
    assert v.kpn.base_kzt == 4_137_000
    assert v.kpn.rate == 0.05                  # ст. 682 п. 1 пп. 4)
    assert v.kpn.amount_kzt == 206_850
    assert v.kpn.convention_applied is False   # без сертификата освобождения нет
    assert v.graphs["F"] == "1170"
    assert v.vat.applicable is False


# ── 3. Россия, дивиденды, доля 70 % ────────────────────────────────────────

def test_golden_russia_dividends_share_70_is_now_a_question_not_a_number():
    """7 000 000 ₸, доля 70 % — с редакции справочника 1.5.0 движок числа не даёт.

    ПОЧЕМУ КОНТРОЛЬНОЕ ЧИСЛО ПУБЛИКАЦИИ БОЛЬШЕ НЕ ОЖИДАЕТСЯ. Официальный
    построчный разбор применяет к этой строке 15 % и получает 1 050 000 ₸.
    Это верно для позиции пп. 5) п. 1 ст. 682. Но подпункт 5) дословно
    исключает доходы подпунктов 6)–7), а подпункт 6) относится ровно к
    дивидендам лицу с долей 25 % и выше и даёт 5 % в пределах 230 000 МРП.
    Дополнительных условий, включая срок владения, ни ст. 680, ни ст. 681
    не содержат. Основание, по которому публикация выбрала 15 %, в ней
    не раскрыто.

    Решение владельца от 19.08.2026: позицию не выбираем. Расхождение
    с публикацией принято сознательно — цена вопроса на этой сумме 700 000 ₸,
    и отдавать её молча в пользу одной из двух позиций нельзя.
    """
    v = run(base(**{
        "S1.1": Q1_2026, "S1.5": "KZT", "S2.3": "RU", "S5.1": DIVIDENDS,
        "S5.8": {"share_pct": 70}, "S7.2": "no",
        "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 7_000_000.0, "S4.5": 1.0,
    }))

    assert v.kpn.base_kzt == 7_000_000        # база известна, спорна только ставка
    assert v.kpn.applicable is None
    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert v.graphs["F"] == "1100"
    assert not v.graphs.get("G")               # R-FORM-04
    assert "F-DIV-25" in v.flags
    assert len(v.kpn.positions) == 2
