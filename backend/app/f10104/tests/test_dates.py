"""Группа R-DATE: норма ст. 684 п. 1, дата курса и срок перечисления.

Главное, что проверяется здесь, — не арифметика дат, а то, что пользователю
НЕ ЗАДАЁТСЯ вопрос «начислено или выплачено». Все восемь правил выводятся
из фактов: две даты, отнесение на вычеты, способ расчёта. Если однажды в
разрешитель придёт ответ вида «это аванс» — значит, выбор переложили обратно
на бухгалтера, а ровно от этого модуль и защищает.
"""
from datetime import date

import pytest

from app.f10104.dates import (LATER_DATE_HINT, deadline_after_declaration,
                              deadline_after_month, resolve)

ACT = date(2026, 2, 20)
PAY = date(2026, 3, 30)


# ── Арифметика сроков ──────────────────────────────────────────────────────

def test_deadline_is_25_days_after_the_end_of_the_month():
    """Не 25 дней от даты выплаты, а 25 дней после ОКОНЧАНИЯ месяца выплаты."""
    assert deadline_after_month(date(2026, 3, 30)) == date(2026, 4, 25)
    assert deadline_after_month(date(2026, 3, 1)) == date(2026, 4, 25)
    assert deadline_after_month(date(2026, 2, 10)) == date(2026, 3, 25)
    assert deadline_after_month(None) is None


def test_deadline_after_declaration_counts_from_next_year_march():
    """Декларация за 2026 сдаётся 31.03.2027, плюс десять дней — 10.04.2027."""
    assert deadline_after_declaration(2026) == date(2027, 4, 10)


# ── Восемь правил ──────────────────────────────────────────────────────────

def test_r_date_01_ordinary_payment_uses_the_payment_date():
    """Акт есть, оплата не раньше акта — пп. 1), курс на дату выплаты."""
    r = resolve({"S4.1": ACT, "S4.2": PAY})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-01", "пп. 1)")
    assert r.fx_date == PAY
    assert r.deadline == date(2026, 4, 25)
    assert r.obligation_arisen


def test_r_date_02_open_advance_has_no_rate_date_yet():
    """Аванс без акта: дата начисления неизвестна, обязанность не наступила.

    Курс на дату аванса брать НЕЛЬЗЯ — это самая дорогая ошибка в ветке."""
    r = resolve({"S4.2": PAY})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-02", "пп. 3)")
    assert r.fx_date is None
    assert r.fx_date != PAY
    assert not r.obligation_arisen
    assert r.control_date == date(2026, 3, 31)


def test_r_date_03_closed_advance_uses_the_accrual_date():
    """Аванс закрыт актом — курс на дату акта, а не на дату аванса."""
    act = date(2026, 4, 15)
    r = resolve({"S4.1": act, "S4.2": PAY})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-03", "пп. 3)")
    assert r.fx_date == act
    assert r.deadline == date(2026, 5, 25)


def test_r_date_04_partial_advance_splits_into_two_norms():
    """Одна операция, две нормы, два срока — реальный случай, которого не было.

    Аванс идёт по пп. 3) с курсом на дату начисления, остаток по пп. 1)
    с курсом на дату выплаты остатка. Сроки считаются отдельно и попадают
    в разные месяцы.
    """
    r = resolve({
        "S4.1": date(2026, 4, 15), "S4.2": PAY, "S4.4": 10_000.0,
        "S4.2a": {"mode": "partial", "advance_amount": 4_000.0,
                  "rest_payment_date": date(2026, 5, 20)},
    })

    assert r.rule_id == "R-DATE-04"
    assert len(r.parts) == 2

    advance, rest = r.parts
    assert (advance.subparagraph, advance.fx_date, advance.deadline) == (
        "пп. 3)", date(2026, 4, 15), date(2026, 5, 25))
    assert (rest.subparagraph, rest.fx_date, rest.deadline) == (
        "пп. 1)", date(2026, 5, 20), date(2026, 6, 25))
    assert advance.amount_fx == 4_000
    assert rest.amount_fx == 6_000            # остаток считается, а не спрашивается
    assert advance.deadline != rest.deadline  # два срока, не один


def test_r_date_04_without_the_rest_paid_keeps_a_control_date():
    """Остаток ещё не выплачен: по нему обязанность не наступила, но аванс
    уже посчитан. Половина операции не должна тянуть вторую в неизвестность."""
    r = resolve({
        "S4.1": date(2026, 4, 15), "S4.2": PAY, "S4.4": 10_000.0,
        "S4.2a": {"mode": "partial", "advance_amount": 4_000.0},
    })

    advance, rest = r.parts
    assert advance.fx_date == date(2026, 4, 15) and advance.deadline
    assert rest.fx_date is None and not rest.fx_date_known
    assert r.control_date == date(2026, 4, 30)


def test_r_date_05_counter_supply_beats_the_ordinary_order():
    """Встречная поставка резидента — пп. 4), курс на дату начисления,
    даже если деньги перечислялись позже акта."""
    r = resolve({"S2.1": "counter_supply", "S4.1": ACT, "S4.2": PAY})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-05", "пп. 4)")
    assert r.fx_date == ACT
    assert "встречных обязательств" in r.explanation


def test_counter_supply_is_asked_once_not_twice():
    """Один и тот же факт спрашивается одним вопросом. Ответ принимается
    и из способа расчёта, и из отдельного вопроса ТЗ — но не требует обоих."""
    from_method = resolve({"S2.1": "counter_supply", "S4.1": ACT, "S4.2": PAY})
    from_question = resolve({"S4.7": "yes", "S4.1": ACT, "S4.2": PAY})

    assert from_method.rule_id == from_question.rule_id == "R-DATE-05"


def test_r_date_06_deduction_without_payment_uses_the_period_end():
    """Отнесено на вычеты без выплаты: курс на 31 декабря налогового периода,
    срок — десять дней после срока сдачи декларации."""
    r = resolve({"S4.1": ACT, "S4.6": {"deducted": True, "year": 2026}})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-06", "пп. 2)")
    assert r.fx_date == date(2026, 12, 31)
    assert r.deadline == date(2027, 4, 10)


def test_r_date_07_no_payment_no_deduction_means_no_obligation_yet():
    """Ни выплаты, ни вычетов — обязанность не наступила. Это законное
    состояние, а не незаполненная анкета, и ноль здесь был бы враньём."""
    r = resolve({"S4.1": ACT, "S4.6": {"deducted": False}})

    assert r.rule_id == "R-DATE-07"
    assert r.subparagraph is None
    assert not r.obligation_arisen
    assert r.control_date and r.control_reason


def test_r_date_08_long_debt_falls_back_to_subparagraph_one():
    """Долговые бумаги с погашением позже срока: вместо пп. 2) действует
    пп. 1), то есть считаем от фактической выплаты."""
    r = resolve({"S4.1": ACT,
                 "S4.6": {"deducted": True, "year": 2026, "long_debt": True}})

    assert (r.rule_id, r.subparagraph) == ("R-DATE-08", "пп. 1)")
    assert r.fx_date is None
    assert not r.obligation_arisen


# ── Принцип, ради которого всё это ─────────────────────────────────────────

@pytest.mark.parametrize("answers", [
    {"S4.1": ACT, "S4.2": PAY},
    {"S4.2": PAY},
    {"S4.1": date(2026, 4, 15), "S4.2": PAY},
    {"S4.1": ACT, "S4.6": {"deducted": True, "year": 2026}},
    {"S4.1": ACT, "S4.6": {"deducted": False}},
    {"S2.1": "counter_supply", "S4.1": ACT, "S4.2": PAY},
])
def test_the_user_is_never_asked_whether_it_is_an_advance(answers):
    """Разрешитель обязан обходиться фактами. Ни один из вариантов не читает
    ответ «аванс или обычная выплата» — стадия выводится из двух дат."""
    assert "S2.1" not in answers or answers["S2.1"] != "advance"
    r = resolve(answers)

    assert r.rule_id.startswith("R-DATE-")
    assert r.explanation


@pytest.mark.parametrize("answers,expected", [
    ({"S4.1": ACT, "S4.2": PAY}, "R-DATE-01"),
    ({"S4.2": PAY}, "R-DATE-02"),
    ({"S4.1": date(2026, 4, 15), "S4.2": PAY}, "R-DATE-03"),
    ({"S2.1": "counter_supply", "S4.1": ACT}, "R-DATE-05"),
    ({"S4.1": ACT, "S4.6": {"deducted": True, "year": 2026}}, "R-DATE-06"),
    ({"S4.1": ACT}, "R-DATE-07"),
    ({}, "R-DATE-00"),
])
def test_every_combination_resolves_to_exactly_one_rule(answers, expected):
    """Развилки не должны перекрываться: один набор фактов — одно правило."""
    assert resolve(answers).rule_id == expected


def test_explanation_never_uses_the_forbidden_question_form():
    """Объяснение говорит, ЧТО применилось и почему, а не переспрашивает.

    Формулировка «начислено или выплачено?» в тексте вывода означала бы, что
    выбор вернули пользователю после того, как движок его уже сделал.
    """
    for answers in ({"S4.1": ACT, "S4.2": PAY}, {"S4.2": PAY},
                    {"S4.1": ACT, "S4.6": {"deducted": True, "year": 2026}}):
        text = resolve(answers).explanation
        assert "начислено или выплачено" not in text.lower()
        assert "?" not in text


def test_later_date_hint_is_marked_as_a_self_check_not_a_norm():
    """Подсказки «берите более позднюю дату» в кодексе нет. Подавать её как
    норму нельзя — под каждый случай там своё правило."""
    assert "не норма" in LATER_DATE_HINT
    assert "проверить себя" in LATER_DATE_HINT


# ── Две контрольные даты, которые нельзя сливать ───────────────────────────

def test_the_two_control_dates_coexist_and_differ():
    """У открытого аванса контрольных дат ДВЕ, и они про разное.

    R-DATE ставит «вернуться, когда подпишут акт» — это про срок уплаты:
    пока акта нет, дата курса неизвестна и обязанность не наступила.
    F-ADVANCE ставит «через 12 месяцев» — это про ст. 679 п. 1 пп. 5):
    неотработанный аванс сам становится доходом нерезидента, независимо
    от конвенции.

    Слить их в одно поле — значит показать бухгалтеру одну дату вместо двух,
    и пропущенной окажется вторая: та, о которой никто не помнит, потому что
    она наступает через год и не связана ни с каким документом.
    """
    from datetime import date as d  # noqa: PLC0415

    from app.f10104.engine import evaluate  # noqa: PLC0415
    from app.f10104.rules import get_rules  # noqa: PLC0415

    from .answers import base  # noqa: PLC0415

    answers = base(**{
        "S2.3": "IN", "S5.1": "services", "S5.5": "consulting",
        "S6.1": "outside", "S7.2": "no", "S1.5": "USD",
        "S4.1": None, "S4.2": d(2026, 3, 20), "S4.4": 30000.0, "S4.5": 500.0,
    })
    v = evaluate(answers, refbooks=get_rules(), as_of_date=d(2026, 3, 31))

    assert v.date_rule.rule_id == "R-DATE-02"

    near = v.date_rule.control_date          # вернуться после акта
    far = v.advance_control_date             # аванс станет доходом

    assert near is not None, "потеряна контрольная дата правила R-DATE"
    assert far is not None, "потеряна контрольная дата F-ADVANCE"
    assert near != far, "две контрольные даты слились в одну"
    assert near < far, "порядок дат перепутан: ближняя должна быть раньше"

    assert near == d(2026, 3, 31)            # конец месяца аванса
    assert far == d(2027, 3, 20)             # выплата плюс 12 месяцев
    assert "F-ADVANCE" in v.flags
    assert v.date_rule.control_reason        # у ближней есть своё объяснение
