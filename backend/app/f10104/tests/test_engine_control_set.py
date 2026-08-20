"""Контрольный набор из официального разбора построчного заполнения формы
101.04 за I квартал 2026 (ТОО «Жарык») — ТЗ §7, таблицы «Контрольный набор»
и «Суммы контрольного набора».

Проверяется и поведение (ставка, код дохода, конвенция, попадание в форму),
и арифметика: база, ставка и КПН по каждой строке плюс строки основного
расчёта 101.04.001 и 101.04.002 по месяцам квартала и итогом.

"""
from datetime import date



from app.f10104.rules import get_rules

from .answers import (
    base, ADVANCE, DIVIDENDS, IN_KZ, OUTSIDE_KZ, PENALTY, RENT, ROYALTY,
    SERVICES, TRANSPORT_INTL,
)

Q1_2026 = {"quarter": 1, "year": 2026}

# Месяц квартала → дата выплаты. Месяц определяет строку 101.04.001/002.
M1, M2, M3 = date(2026, 1, 20), date(2026, 2, 20), date(2026, 3, 20)


def run(answers: dict):
    from app.f10104.engine import evaluate  # noqa: PLC0415

    return evaluate(answers, refbooks=get_rules(), as_of_date=date(2026, 3, 31))


def row(**over) -> dict:
    """Строка контрольного набора: I квартал 2026, выплата юрлицу-нерезиденту."""
    return base(**{"S1.1": Q1_2026, "S4.1": M1, "S4.2": M1, **over})


def exempt_by_convention(**over) -> dict:
    """Условия ст. 705 выполнены: сертификат есть, ПУ нет, conduit нет."""
    return row(**{"S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.6": "no", **over})


# ── Строки набора: ответы под каждую строку таблицы «Суммы контрольного
#    набора». Суммы и курсы — дословно оттуда.

ABC_GB = exempt_by_convention(**{
    "S2.3": "GB", "S5.1": SERVICES, "S5.5": "legal", "S6.1": OUTSIDE_KZ,
    "S1.5": "GBP", "S4.4": 10500.0, "S4.5": 671.44, "S4.1": M1, "S4.2": M1,
})
MBA_DE = exempt_by_convention(**{
    "S2.3": "DE", "S5.1": SERVICES, "S5.5": "audit", "S6.1": IN_KZ,
    "S1.5": "EUR", "S4.4": 6500.0, "S4.5": 586.00, "S4.1": M1, "S4.2": M1,
})
AAA_TH = row(**{
    "S2.3": "TH", "S5.1": PENALTY, "S7.2": "no",
    "S1.5": "THB", "S4.4": 5740.0, "S4.5": 16.33, "S4.1": M1, "S4.2": M1,
})
BBB_NL = row(**{
    "S2.3": "NL", "S2.1": ADVANCE, "S5.1": TRANSPORT_INTL,
    "S7.2": "yes", "S7.3": "no",                    # сертификата нет
    "S1.5": "EUR", "S4.4": 7000.0, "S4.5": 591.00, "S4.1": M2, "S4.2": M2,
})
GLOBAL_US = exempt_by_convention(**{
    "S2.3": "US", "S5.1": RENT, "S5.5": "rent_movable", "S6.1": IN_KZ,
    "S8.2": "exempt_from_apostille",                # форма 6166, апостиль не нужен
    "S1.5": "USD", "S4.4": 10500.0, "S4.5": 503.90, "S4.1": M2, "S4.2": M2,
})
PPP_ME = row(**{
    "S2.3": "OFF54", "S5.1": RENT, "S5.5": "rent_vehicle", "S6.1": OUTSIDE_KZ,
    "S7.2": "no", "S1.5": "EUR", "S4.4": 4500.0, "S4.5": 594.50,
    "S5.9": {"accrued": True, "accrued_amount": 4000.0},   # начислено 4 000 из 4 500
    "S4.1": M3, "S4.2": M3,
})
CCC_RU = exempt_by_convention(**{
    "S2.3": "RU", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": OUTSIDE_KZ,
    "S1.5": "RUB", "S4.4": 20000.0, "S4.5": 6.05, "S4.1": M3, "S4.2": M3,
})
RRR_CA = exempt_by_convention(**{
    "S2.3": "CA", "S5.1": SERVICES, "S5.5": "audit", "S6.1": OUTSIDE_KZ,
    "S1.5": "CAD", "S4.4": 20000.0, "S4.5": 363.00, "S4.1": M3, "S4.2": M3,
})
SORT_RU = row(**{
    "S2.3": "RU", "S5.1": DIVIDENDS, "S5.8": {"share_pct": 70, "position": "pp5_15pct",
              "position_basis": "построчный разбор С. Зуевой и Г. Умрихиной"}, "S7.2": "no",
    "S1.5": "KZT", "S4.4": 7_000_000.0, "S4.5": 1.0, "S4.1": M3, "S4.2": M3,
})
PROBA_RU = row(**{
    "S2.3": "RU", "S5.1": DIVIDENDS, "S5.8": {"share_pct": 30, "position": "pp5_15pct",
              "position_basis": "построчный разбор С. Зуевой и Г. Умрихиной"}, "S7.2": "no",
    "S1.5": "KZT", "S4.4": 3_000_000.0, "S4.5": 1.0, "S4.1": M3, "S4.2": M3,
})

# ДВЕ СТРОКИ С ДИВИДЕНДАМИ ПИНЯТ ПОЗИЦИЮ пп. 5). С редакции справочника 1.5.0
# ставка при доле 25 % и выше спорна, и по умолчанию движок числа не даёт.
# Публикация применила 15 % — это позиция пп. 5). Чтобы регрессия против
# публикации продолжала работать, набор выбирает её явно, с обоснованием
# «построчный разбор С. Зуевой и Г. Умрихиной». Так тест по-прежнему ловит
# расхождения с источником, а поведение по умолчанию остаётся нетронутым.

ALL_ROWS = [ABC_GB, MBA_DE, AAA_TH, BBB_NL, GLOBAL_US,
            PPP_ME, CCC_RU, RRR_CA, SORT_RU, PROBA_RU]


# ── Построчная арифметика ──────────────────────────────────────────────────

def test_control_abc_gb_legal_services_exempt():
    """10 500 GBP × 671,44 = 7 050 120 ₸ · освобождение по конвенции · КПН 0.
    Графа Q = сумма дохода. Код 1037 (не 1030, см. сноску ТЗ)."""
    v = run(ABC_GB)

    assert v.kpn.taxable is True          # облагаемо по пп. 3) п. 1 ст. 679
    assert v.kpn.base_kzt == 7_050_120
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.kpn.amount_kzt == 0
    assert v.graphs["F"] == "1037"
    assert v.graphs["Q"] == 7_050_120


def test_control_mba_de_audit_in_kz_exempt():
    """6 500 EUR × 586,00 = 3 809 000 ₸ · освобождение по конвенции · КПН 0.
    Код 1020 — услуги оказаны в РК."""
    v = run(MBA_DE)

    assert v.kpn.base_kzt == 3_809_000
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.kpn.amount_kzt == 0
    assert v.graphs["F"] == "1020"


def test_control_aaa_th_penalty_20():
    """5 740 THB × 16,33 = 93 734 ₸ · 20 % · 18 747 ₸.
    пп. 11) п. 1 ст. 679, конвенции с Таиландом нет."""
    v = run(AAA_TH)

    assert v.kpn.base_kzt == 93_734
    assert v.kpn.rate == 0.20
    assert v.kpn.amount_kzt == 18_747
    assert v.kpn.convention_applied is False
    assert v.graphs["F"] == "1090"


def test_control_bbb_nl_intl_transport_5():
    """7 000 EUR × 591,00 = 4 137 000 ₸ · 5 % · 206 850 ₸.
    Без сертификата конвенция не применяется. НДС не возникает."""
    v = run(BBB_NL)

    assert v.kpn.base_kzt == 4_137_000
    assert v.kpn.rate == 0.05
    assert v.kpn.amount_kzt == 206_850
    assert v.kpn.convention_applied is False
    assert v.graphs["F"] == "1170"
    assert v.vat.applicable is False


def test_control_global_us_rent_in_kz_exempt_without_apostille():
    """10 500 USD × 503,90 = 5 290 950 ₸ · освобождение по конвенции · КПН 0.

    Для форм 6166 США апостиль не требуется по взаимному соглашению
    компетентных органов (ст. 702 п. 2 + ст. 232). Код 1140.
    """
    v = run(GLOBAL_US)

    assert v.kpn.base_kzt == 5_290_950
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.kpn.amount_kzt == 0
    assert v.graphs["F"] == "1140"


def test_control_ppp_montenegro_partial_accrual():
    """Предоплата 4 500 EUR, начислено 4 000 → база 4 000 × 594,50 = 2 378 000 ₸ ·
    20 % · 475 600 ₸. Остаток 500 EUR не облагается, 12 месяцев не прошли
    (R-KPN-19). Офшор → ставка независимо от места оказания."""
    v = run(PPP_ME)

    assert v.kpn.base_kzt == 2_378_000          # 4 000 EUR, не 4 500
    assert v.kpn.rate == 0.20
    assert v.kpn.amount_kzt == 475_600
    assert v.graphs["F"] == "1040"
    assert v.graphs["D"] == "54"
    assert "F-OFFSHORE" in v.flags


def test_control_ccc_ru_consulting_exempt():
    """20 000 RUB × 6,05 = 121 000 ₸ · освобождение по конвенции · КПН 0.
    Апостиль не нужен — обмен нотами РК–РФ 2016 г. Код 1033 (не 1030)."""
    v = run(CCC_RU)

    assert v.kpn.base_kzt == 121_000
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.graphs["F"] == "1033"


def test_control_rrr_ca_audit_exempt():
    """20 000 CAD × 363,00 = 7 260 000 ₸ · освобождение по конвенции · КПН 0.
    Код 1036 (не 1030)."""
    v = run(RRR_CA)

    assert v.kpn.base_kzt == 7_260_000
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.graphs["F"] == "1036"


def test_control_sort_ru_dividends_share_70():
    """7 000 000 ₸ × 15 % = 1 050 000 ₸ при явно выбранной позиции пп. 5).

Позиция выбрана набором явно — по умолчанию движок числа не даёт.
    """
    v = run(SORT_RU)

    assert v.kpn.base_kzt == 7_000_000
    assert v.kpn.rate == 0.15
    assert v.kpn.amount_kzt == 1_050_000
    assert v.graphs["F"] == "1100"
    assert not v.graphs.get("G")
    assert v.kpn.position_chosen == "pp5_15pct"
    assert v.kpn.position_basis                      # без обоснования выбора нет
    assert "F-DIV-25-RESOLVED" in v.flags


def test_control_proba_ru_dividends_share_30():
    """3 000 000 ₸ × 15 % = 450 000 ₸ при той же явно выбранной позиции."""
    v = run(PROBA_RU)

    assert v.kpn.base_kzt == 3_000_000
    assert v.kpn.rate == 0.15
    assert v.kpn.amount_kzt == 450_000
    assert v.graphs["F"] == "1100"
    assert "F-DIV-25-RESOLVED" in v.flags


# ── «Brain»: предоплата без начисления в форму не попадает ─────────────────

def test_control_brain_au_advance_only_is_not_in_the_form():
    """Австралия, роялти, только предоплата. Доход не начислен → движок не
    должен создавать строку в форме вовсе (R-KPN-19)."""
    v = run(row(**{
        "S2.3": "AU", "S2.1": ADVANCE, "S5.1": ROYALTY, "S7.2": "no",
        "S1.5": "USD", "S4.4": 12000.0, "S4.5": 500.0,
        "S5.9": {"accrued": False},
    }))

    assert v.reporting.reported_in_form is False
    assert v.kpn.base_kzt == 0
    assert v.kpn.amount_kzt == 0


# ── Строки основного расчёта ───────────────────────────────────────────────

def _form():
    from app.f10104.engine import aggregate_form  # noqa: PLC0415

    return aggregate_form([run(a) for a in ALL_ROWS])


def test_control_form_line_002_tax_by_month_and_total():
    """Строка 101.04.002 — налог по месяцам квартала и итогом.
    Здесь публикация внутренне согласована: 18 747 + 206 850 + 1 975 600 = 2 201 197."""
    assert _form().line_002 == {
        "I": 18_747,
        "II": 206_850,
        "III": 1_975_600,
        "IV": 2_201_197,
    }


def test_control_form_line_001_income_months_2_and_3():
    """Строка 101.04.001 за II и III месяцы квартала — сходится построчно."""
    line = _form().line_001

    assert line["II"] == 9_427_950     # BBB 4 137 000 + Global L 5 290 950
    assert line["III"] == 19_759_000   # PPP + CCC + RRR + СОРТ + ПРОБА


def test_control_form_line_001_income_month_1_and_total():
    """Строка 101.04.001 за I месяц и итог за квартал.

    Публикация в этом месте ошибалась: помесячная разбивка теряла доход AAA
    (93 734 ₸), хотя её налог 18 747 ₸ в 101.04.002 учитывала. Верные числа —
    построчная сумма (ТЗ §8).
    """
    line = _form().line_001

    assert line["I"] == 10_952_854     # ABC 7 050 120 + MBA 3 809 000 + AAA 93 734
    assert line["IV"] == 40_139_804
