"""20 тест-кейсов приёмки — дословный перенос таблицы ТЗ §7.

Каждый тест назван T1…T20 по номеру из ТЗ, чтобы строку таблицы и проверку
можно было сверить глазами. Ожидания взяты из колонки «Ожидаемый вывод» и не
дополнены рассуждениями: где ТЗ говорит `manual_review`, тест требует
`manual_review`, а не «правильный» ответ.

"""
from datetime import date

import pytest

from app.f10104.rules import get_rules

from .answers import (
    base, ADVANCE, BRANCH_KZ, GOODS, INDIVIDUAL,
    IN_KZ, OFFSET, OUTSIDE_KZ, ROYALTY, SERVICES, TRANSPORT_INTL,
)


def run(answers: dict, on: date = date(2026, 9, 30), usd_rate: float | None = None):
    from app.f10104.engine import evaluate  # noqa: PLC0415 — см. комментарий выше

    return evaluate(answers, refbooks=get_rules(), as_of_date=on, usd_rate=usd_rate)


# ── T1–T3. Дизайн из Польши: конвенция, её отсутствие, неплательщик НДС ────

POLAND_DESIGN = {
    "S2.3": "PL",
    "S5.1": SERVICES,
    "S5.5": "design",
    "S6.1": OUTSIDE_KZ,
    "S1.5": "EUR",
    "S4.4": 5000.0,
    "S4.5": 500.0,
}


def test_T1_poland_design_with_certificate():
    """Освобождение по конвенции (ст. 705), ставка 0, графа Q; в 101.04
    отражается. НДС — место реализации РК (ст. 459 п. 2 пп. 4), 16 %."""
    v = run(base(**{**POLAND_DESIGN, "S7.2": "yes", "S7.3": "yes",
                    "S7.4": "no", "S7.6": "no"}))

    assert v.kpn.taxable is True          # облагаемо по ст. 679 п. 1 пп. 3)
    assert v.kpn.convention_applied is True
    assert v.kpn.rate == 0.0
    assert v.kpn.amount_kzt == 0
    assert v.graphs["Q"] == v.kpn.base_kzt
    assert v.reporting.form_101_04_required is True
    assert v.vat.applicable is True
    assert v.vat.rate == 0.16


def test_T2_poland_design_without_certificate():
    """20 % удерживается + маршрут возврата (ст. 699–701). НДС 16 %."""
    v = run(base(**{**POLAND_DESIGN, "S7.2": "yes", "S7.3": "no"}))

    assert v.kpn.convention_applied is False
    assert v.kpn.rate == 0.20
    assert v.kpn.amount_kzt == 500_000        # 5 000 × 500 × 20 %
    assert any("699" in b for b in v.kpn.basis)
    assert v.vat.applicable is True


def test_T3_poland_design_buyer_not_vat_registered():
    """НДС не возникает (ст. 454 п. 1) + предупреждение о пороге 43 250 000 ₸."""
    v = run(base(**{**POLAND_DESIGN, "S1.4": "no", "S7.2": "yes", "S7.3": "yes"}))

    assert v.vat.applicable is False
    assert "454" in v.vat.basis
    assert "F-VAT-THRESHOLD" in v.flags


# ── T4. Хостинг из Германии ────────────────────────────────────────────────

def test_T4_germany_hosting():
    """КПН не облагается (ст. 681 п. 1 пп. 5) — хостинг не в перечне пп. 3).
    НДС — manual_review."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "hosting",
                    "S6.1": OUTSIDE_KZ, "S7.2": "no", "S4.4": 4000.0,
                    "S4.5": 500.0}))

    assert v.kpn.taxable is False
    assert any("681" in b for b in v.kpn.basis)
    assert v.vat.applicable is None            # manual_review, а не «нет»
    assert v.confidence == "manual_review"


# ── T5. Офшор ──────────────────────────────────────────────────────────────

def test_T5_bvi_consulting_certificate_does_not_help():
    """20 %, конвенция не применяется (ст. 682 п. 2), сертификат не помогает.

    Британские Виргинские острова входят в запись № 45 перечня № 492
    (Великобритания в части заморских территорий); код страны в графе D —
    порядковый номер государства, а не территории.
    """
    v = run(base(**{"S2.3": "OFF45", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": OUTSIDE_KZ, "S7.2": "yes", "S7.3": "yes",
                    "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.kpn.rate == 0.20
    assert v.kpn.convention_applied is False
    assert "F-OFFSHORE" in v.flags
    assert v.graphs["D"] == "45"
    assert v.graphs["F"] == "1040"


# ── T6–T7. Смешанный контракт ──────────────────────────────────────────────

def test_T6_china_equipment_plus_supervision_split():
    """Станок — не доход из источников в РК (ст. 680 п. 1 пп. 4). Шефмонтаж —
    20 % (ст. 679 п. 1 пп. 2). НДС по монтажу — ст. 459 п. 2 пп. 2), место
    выполнения РК → 16 %.

    База по КПН — только шефмонтаж (S5.4a), стоимость станка в неё не входит
    (ст. 680 п. 1 пп. 4): 10 000 USD × 500 = 5 000 000 ₸, налог 1 000 000 ₸.
    """
    v = run(base(**{"S2.3": "CN", "S5.1": GOODS, "S5.2": "yes", "S5.3": "yes",
                    "S5.4": "yes", "S5.4a": 10000.0, "S5.5": "install",
                    "S6.1": IN_KZ, "S7.2": "no", "S1.5": "USD",
                    "S4.4": 110000.0, "S4.5": 500.0}))

    assert v.kpn.taxable is True
    assert v.kpn.rate == 0.20
    assert v.kpn.base_kzt == 5_000_000        # шефмонтаж, не 110 000 USD
    assert v.kpn.amount_kzt == 1_000_000
    assert "F-MIXED" not in v.flags
    assert v.vat.applicable is True
    assert v.vat.base_kzt == 5_000_000


def test_T7_china_equipment_plus_supervision_not_split():
    """Суммы не выделены → F-MIXED, облагается совокупная сумма (ст. 683 п. 8)."""
    v = run(base(**{"S2.3": "CN", "S5.1": GOODS, "S5.2": "yes", "S5.3": "yes",
                    "S5.4": "no", "S5.5": "install", "S6.1": IN_KZ,
                    "S7.2": "no", "S1.5": "USD", "S4.4": 110000.0,
                    "S4.5": 500.0}))

    assert "F-MIXED" in v.flags
    assert v.kpn.base_kzt == 55_000_000        # вся сумма, без выделения
    assert any("683" in b for b in v.kpn.basis)


# ── T8. Аванс ──────────────────────────────────────────────────────────────

def test_T8_advance_to_india():
    """Срок — 25 к.д. после месяца начисления (ст. 684 п. 1 пп. 3).
    F-ADVANCE, контрольная дата — выплата + 12 месяцев."""
    v = run(base(**{"S2.3": "IN", "S2.1": ADVANCE, "S5.1": SERVICES,
                    "S5.5": "consulting", "S6.1": OUTSIDE_KZ, "S7.2": "no",
                    "S1.5": "USD", "S4.2": date(2026, 3, 20), "S4.4": 30000.0,
                    "S4.5": 500.0}),
            on=date(2026, 3, 31))

    assert "F-ADVANCE" in v.flags
    assert v.advance_control_date == date(2027, 3, 20)
    assert any("684" in b for b in v.kpn.basis)


# ── T9. Роялти ─────────────────────────────────────────────────────────────

def test_T9_russia_software_licence_support_not_split():
    """Вся сумма как роялти, 15 % по НК. F-ROYALTY. НДС 16 % (права на ИС)."""
    v = run(base(**{"S2.3": "RU", "S5.1": ROYALTY, "S5.6": "yes", "S5.7": "no",
                    "S7.2": "no", "S1.5": "USD", "S4.4": 20000.0,
                    "S4.5": 500.0}))

    assert v.kpn.rate == 0.15
    assert "F-ROYALTY" in v.flags
    assert any("683" in b for b in v.kpn.basis)   # п. 5 — техподдержка не выделена
    assert v.vat.applicable is True


# ── T10–T11. Физлица: маршрут на 200.00 ────────────────────────────────────

def test_T10_individual_uzbekistan_gph():
    """Не 101.04. ИПН 20 % (ГПХ), форма 200.00 прил. 200.02.
    ОПВ/ВОСМС/СО не применяются — Узбекистан не в ЕАЭС."""
    v = run(base(**{"S2.2": INDIVIDUAL, "S2.3": "UZ", "S5.1": SERVICES,
                    "S5.5": "design", "S6.1": OUTSIDE_KZ}))

    assert v.route == "individual_200_00"
    assert v.reporting.form_101_04_required is False
    assert v.individual.ipn_rate == 0.20
    assert v.individual.opv is False
    assert v.individual.vosms is False
    assert v.individual.so is False


def test_T11_individual_kyrgyzstan_eaeu():
    """ЕАЭС: ИПН 20 % + ОПВ 10 % + ВОСМС 2 % + соцотчисления 5 %.
    Блокер — нужен казахстанский ИИН."""
    v = run(base(**{"S2.2": INDIVIDUAL, "S2.3": "KG", "S5.1": SERVICES,
                    "S5.5": "design", "S6.1": OUTSIDE_KZ}))

    assert v.route == "individual_200_00"
    assert v.individual.ipn_rate == 0.20
    assert v.individual.opv is True
    assert v.individual.vosms is True
    assert v.individual.so is True
    assert v.individual.requires_iin is True



def test_T11a_ipn_transfer_deadline_differs_from_kpn():
    """Срок перечисления ИПН — 25 число месяца, следующего за месяцем
    удержания (ст. 692 п. 6), а НЕ 25 число второго месяца после квартала,
    как у КПН (ст. 684). Их регулярно путают, поэтому проверяем отдельно.

    Удержание при выплате 20.07.2026 → перечислить до 25.08.2026.
    Форма — 200.00, приложение 200.02 (ст. 694).
    """
    v = run(base(**{"S2.2": INDIVIDUAL, "S2.3": "UZ", "S5.1": SERVICES,
                    "S5.5": "design", "S6.1": OUTSIDE_KZ,
                    "S4.2": date(2026, 7, 20)}))

    assert v.route == "individual_200_00"
    assert v.deadlines.ipn_payment == date(2026, 8, 25)
    assert v.individual.form == "200.00"
    assert v.individual.appendix == "200.02"

# ── T12–T13. Постоянное учреждение ─────────────────────────────────────────

def test_T12_turkey_branch_contract_with_head_office():
    """Договор с головным офисом, СФ от головного → 20 % без вычетов
    (ст. 690), отражается в 101.04."""
    v = run(base(**{"S2.2": BRANCH_KZ, "S2.3": "TR", "S3.1": "yes",
                    "S3.2": "head_office", "S3.3": "no", "S5.1": SERVICES,
                    "S5.5": "consulting", "S6.1": IN_KZ, "S7.2": "no",
                    "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.kpn.taxable is True
    assert v.kpn.rate == 0.20
    assert v.reporting.form_101_04_required is True
    assert any("690" in b for b in v.kpn.basis)


def test_T13_turkey_branch_contract_with_branch():
    """Договор с филиалом и СФ от филиала с БИН → КПН не удерживается,
    в 101.04 не отражается (ст. 683 п. 1)."""
    v = run(base(**{"S2.2": BRANCH_KZ, "S2.3": "TR", "S3.1": "yes",
                    "S3.2": "branch", "S3.3": "yes", "S5.1": SERVICES,
                    "S5.5": "consulting", "S6.1": IN_KZ, "S7.2": "no",
                    "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.route == "pe_branch_not_reported"
    assert v.kpn.taxable is False
    assert v.reporting.form_101_04_required is False
    assert any("683" in b for b in v.kpn.basis)


# ── T14–T16. Порог 50 000 USD и обязанность сдавать форму ──────────────────

NON_TAXABLE_SERVICE = {
    "S2.3": "DE", "S5.1": SERVICES, "S5.5": "software_support",
    "S6.1": OUTSIDE_KZ, "S7.2": "no", "S1.5": "USD", "S4.5": 500.0,
}


def test_T14_below_threshold_no_form():
    """20 000 USD за услуги вне РК, облагаемых доходов нет → 101.04 не требуется,
    с оговоркой о спорности трактовки порога."""
    v = run(base(**{**NON_TAXABLE_SERVICE, "S4.4": 20000.0, "S2.5": "УНК-1"}))

    assert v.kpn.taxable is False
    assert v.reporting.form_101_04_required is False
    assert "F-DISCLOSURE-50K" in v.flags


def test_T15_above_threshold_form_required():
    """60 000 USD → форма сдаётся, заполняются графы W/X."""
    v = run(base(**{**NON_TAXABLE_SERVICE, "S4.4": 60000.0, "S2.5": "УНК-1"}))

    assert v.reporting.form_101_04_required is True
    assert v.graphs["W"]
    assert v.graphs["X"]


def test_T16_any_taxable_income_forces_form():
    """Есть облагаемый доход (консультации из Германии) → форма сдаётся
    независимо от суммы, порог не применяется (R-REP-01)."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": OUTSIDE_KZ, "S7.2": "no", "S1.5": "USD",
                    "S4.4": 500.0, "S4.5": 500.0}))

    assert v.kpn.taxable is True
    assert v.reporting.form_101_04_required is True
    assert v.reporting.threshold_applied is False


# ── T17. Разные периоды по НДС и КПН ───────────────────────────────────────

def test_T17_period_mismatch():
    """Акт 28.06.2026, оплата 10.07.2026. НДС — II квартал, срок 25.08.2026.
    КПН и 101.04 — III квартал, срок уплаты 25.08.2026, форма до 16.11.2026."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": IN_KZ, "S7.2": "no", "S1.5": "EUR",
                    "S4.1": date(2026, 6, 28), "S4.2": date(2026, 7, 10),
                    "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.periods.vat_quarter == 2
    assert v.periods.kpn_quarter == 3
    assert v.deadlines.vat_payment == date(2026, 8, 25)
    assert v.deadlines.kpn_payment == date(2026, 8, 25)
    assert v.deadlines.form_101_04 == date(2026, 11, 16)   # перенос с 15.11, воскресенье
    assert "F-PERIOD-MISMATCH" in v.flags


# ── T18. Взаимозачёт ───────────────────────────────────────────────────────

def test_T18_offset_is_payment():
    """Зачёт = выплата дохода (ст. 679 п. 2). КПН 20 %, НДС 16 %."""
    v = run(base(**{"S2.1": OFFSET, "S2.3": "DE", "S5.1": SERVICES,
                    "S5.5": "consulting", "S6.1": OUTSIDE_KZ, "S7.2": "no",
                    "S1.5": "USD", "S4.4": 15000.0, "S4.5": 500.0}))

    assert v.kpn.taxable is True
    assert v.kpn.rate == 0.20
    assert v.vat.applicable is True
    assert any("679" in b for b in v.kpn.basis)


# ── T19. Перевозка ─────────────────────────────────────────────────────────

def test_T19_transport_from_nonresident_no_vat():
    """КПН — международная перевозка 5 %. НДС **не возникает**: место
    реализации определяется по исполнителю (R-VAT-10).

    Условия ст. 459 п. 2 пп. 5) кумулятивны — сначала присутствие исполнителя
    в РК на основе регистрации, и только потом ввоз/вывоз/перевозка по РК.
    У нерезидента-перевозчика первое условие не выполняется.
    F-TRANSPORT остаётся, но как info: это пояснение, а не предупреждение.

    Прежнее ожидание из ТЗ §7 (manual_review) снято решением владельца.
    """
    v = run(base(**{"S2.3": "DE", "S5.1": TRANSPORT_INTL, "S5.5": "transport",
                    "S7.2": "no", "S1.5": "EUR", "S4.4": 8000.0,
                    "S4.5": 500.0}))

    assert v.kpn.rate == 0.05
    assert v.vat.applicable is False
    assert "F-TRANSPORT" in v.flags
    assert v.flag_severity("F-TRANSPORT") == "info"


def test_T19a_freight_forwarding_needs_manual_review():
    """Граница между перевозкой и экспедированием: организация перевозки прямо
    не названа ни в одном подпункте п. 2 ст. 459. Остаточное правило пп. 5)
    даёт «не РК», но при агентской конструкции возможна квалификация по пп. 4).
    Движок вывод не даёт."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "freight_forwarding",
                    "S6.1": OUTSIDE_KZ, "S7.2": "no", "S1.5": "EUR",
                    "S4.4": 8000.0, "S4.5": 500.0}))

    assert v.vat.applicable is None
    assert "F-FORWARDING" in v.flags
    assert v.confidence == "manual_review"


# ── T20. Режим исправления ─────────────────────────────────────────────────

def test_T20_fix_mode_additional_form():
    """Дополнительная 101.04 + перечисление в течение 3 рабочих дней →
    освобождение от штрафа по ч. 1 ст. 279 КоАП. Пеня — 0,05736 % в день."""
    v = run(base(**{"mode": "fix", "S1.1": {"quarter": 1, "year": 2026},
                    "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": IN_KZ, "S7.2": "no", "S4.4": 10000.0,
                    "S4.5": 500.0}))

    assert v.fix.additional_form_required is True
    assert v.fix.penalty_relief_business_days == 3
    assert v.fix.penalty_daily_rate == pytest.approx(0.0005736, rel=1e-6)


# ── Порог раскрытия 50 000 USD в валюте, отличной от доллара ───────────────

NON_TAXABLE_EUR = {
    "S2.3": "DE", "S5.1": SERVICES, "S5.5": "software_support",
    "S6.1": OUTSIDE_KZ, "S7.2": "no", "S1.5": "EUR", "S2.5": "УНК-1",
    "S4.4": 60000.0, "S4.5": 500.0,
}


def test_threshold_in_eur_converted_by_usd_rate():
    """60 000 EUR по курсу 500 = 30 000 000 ₸; при курсе доллара 500 это
    60 000 USD — выше порога, форма сдаётся."""
    v = run(base(**NON_TAXABLE_EUR), usd_rate=500.0)

    assert v.kpn.taxable is False
    assert v.reporting.threshold_checked is True
    assert v.reporting.form_101_04_required is True
    assert "F-THRESHOLD-FX" not in v.flags


def test_threshold_in_eur_below_when_usd_is_expensive():
    """Тот же договор при курсе доллара 700: 30 000 000 / 700 ≈ 42 857 USD —
    ниже порога, форма не требуется."""
    v = run(base(**NON_TAXABLE_EUR), usd_rate=700.0)

    assert v.reporting.threshold_checked is True
    assert v.reporting.form_101_04_required is False


def test_threshold_not_checked_without_usd_rate():
    """Курса доллара на дату нет — порог не проверен. Молча пропускать нельзя:
    выставляем manual_review и флаг, а не «раскрывать нечего»."""
    v = run(base(**NON_TAXABLE_EUR), usd_rate=None)

    assert v.reporting.threshold_checked is False
    assert "F-THRESHOLD-FX" in v.flags
    assert v.confidence == "manual_review"
    assert v.flag_severity("F-THRESHOLD-FX") == "medium"


# ── Три даты — три курса в одной операции ─────────────────────────────────
# Самая частая ошибка ручного расчёта: один курс переиспользуется на всю
# операцию. Дата выплаты, дата начисления и дата совершения оборота — разные
# даты, и курс на каждую свой.

def test_vat_base_uses_turnover_date_rate_not_payment_date():
    """База НДС считается по курсу на дату оборота (ст. 463 п. 2), база КПН —
    по курсу на дату выплаты (ст. 684 п. 1). Курсы разные — базы разные."""
    v = run(base(**{
        "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": IN_KZ,
        "S7.2": "no", "S1.5": "EUR",
        "S4.1": date(2026, 6, 28), "S4.2": date(2026, 7, 10),
        "S4.4": 10000.0,
        "S4.5": 500.0,      # курс на дату выплаты
        "S4.5b": 480.0,     # курс на дату оборота
    }))

    assert v.kpn.base_kzt == 5_000_000        # 10 000 × 500
    assert v.vat.base_kzt == 4_800_000        # 10 000 × 480
    assert v.vat.amount_kzt == 768_000        # 4 800 000 × 16 %
    assert v.fx_used["kpn"] == 500.0
    assert v.fx_used["vat"] == 480.0


def test_advance_uses_accrual_date_rate_for_kpn():
    """При авансе КПН считается по курсу на дату начисления дохода
    (ст. 684 п. 1 пп. 3), а не на дату перечисления денег."""
    v = run(base(**{
        "S2.3": "IN", "S2.1": ADVANCE, "S5.1": SERVICES, "S5.5": "consulting",
        "S6.1": OUTSIDE_KZ, "S7.2": "no", "S1.5": "USD",
        "S4.2": date(2026, 3, 20), "S4.4": 30000.0,
        "S4.5": 500.0,      # курс на дату выплаты аванса
        "S4.5a": 520.0,     # курс на дату начисления
    }), on=date(2026, 3, 31))

    assert v.kpn.base_kzt == 15_600_000       # 30 000 × 520, не × 500
    assert v.fx_used["kpn"] == 520.0


def test_single_rate_still_works_when_only_payment_rate_given():
    """Если отдельные курсы не указаны, всё считается по курсу выплаты —
    поведение по умолчанию не меняется."""
    v = run(base(**{
        "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": IN_KZ,
        "S7.2": "no", "S1.5": "EUR", "S4.4": 10000.0, "S4.5": 500.0,
    }))

    assert v.kpn.base_kzt == v.vat.base_kzt == 5_000_000
    assert v.fx_used["kpn"] == v.fx_used["vat"] == 500.0


def test_single_rate_across_different_dates_is_marked():
    """Даты оборота и выплаты разные, а курс задан один — база НДС молча
    считается по курсу выплаты. Умолчание оставлено, но операция помечается:
    молчаливо давать неверную базу НДС нельзя."""
    answers = {
        "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": IN_KZ,
        "S7.2": "no", "S1.5": "EUR",
        "S4.1": date(2026, 6, 28), "S4.2": date(2026, 7, 10),
        "S4.4": 10000.0, "S4.5": 500.0,
    }

    reused = run(base(**answers))
    assert reused.fx_single_rate_reused is True
    assert reused.vat.base_kzt == 5_000_000       # по курсу выплаты, не оборота
    assert "F-FX-ONE-RATE" in reused.flags
    # medium, а не high: красный в этом продукте означает «конструкция рушится,
    # идите к консультанту». Здесь незаполненное поле, закрывается в два клика.
    assert reused.flag_severity("F-FX-ONE-RATE") == "medium"

    explicit = run(base(**{**answers, "S4.5b": 480.0}))
    assert explicit.fx_single_rate_reused is False
    assert explicit.vat.base_kzt == 4_800_000
    assert "F-FX-ONE-RATE" not in explicit.flags


def test_same_dates_do_not_raise_the_single_rate_marker():
    """Если акт и выплата в один день, один курс — это правильно, а не упущение."""
    v = run(base(**{
        "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": IN_KZ,
        "S7.2": "no", "S1.5": "EUR",
        "S4.1": date(2026, 7, 10), "S4.2": date(2026, 7, 10),
        "S4.4": 10000.0, "S4.5": 500.0,
    }))

    assert v.fx_single_rate_reused is False
    assert "F-FX-ONE-RATE" not in v.flags


def test_period_mismatch_carries_both_periods_and_all_deadlines():
    """T17 целиком: одна операция попадает в две декларации за разные кварталы,
    и это не ошибка. Бухгалтер должен увидеть оба периода и оба срока."""
    v = run(base(**{
        "S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting", "S6.1": IN_KZ,
        "S7.2": "no", "S1.5": "EUR",
        "S4.1": date(2026, 6, 28), "S4.2": date(2026, 7, 10),
        "S4.4": 10000.0, "S4.5": 500.0, "S4.5b": 480.0,
    }))

    assert "F-PERIOD-MISMATCH" in v.flags
    assert v.flag_severity("F-PERIOD-MISMATCH") == "info"   # «нормально, не ошибка»
    assert (v.periods.vat_quarter, v.periods.vat_year) == (2, 2026)
    assert (v.periods.kpn_quarter, v.periods.kpn_year) == (3, 2026)
    assert v.deadlines.vat_payment == date(2026, 8, 25)
    assert v.deadlines.kpn_payment == date(2026, 8, 25)
    assert v.deadlines.form_101_04 == date(2026, 11, 16)
