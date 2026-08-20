"""Блок 2 «Подробнее»: трассировка вывода к ответам.

Проверяется не красота текстов, а три вещи, на которых блок держится:
объяснение не расходится с расчётом, каждая развилка ведёт к конкретному
ответу, и альтернатива показывается только когда она меняет сумму.
"""
from datetime import date

from app.f10104.engine import evaluate
from app.f10104.explain import (NBSP, Counterfactual, Decision, Input,
                                explain, money, percent)
from app.f10104.rules import get_rules

from .answers import base, DIVIDENDS

AS_OF = date(2026, 3, 31)
BASIS = "письмо КГД № 123 от 01.02.2026"


def build(**overrides):
    answers = base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S1.5": "KZT", "S1.4": "yes",
        "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 7_000_000.0, "S4.5": 1.0, **overrides,
    })
    refbooks = get_rules()
    verdict = evaluate(answers, refbooks=refbooks, as_of_date=AS_OF)
    return answers, verdict, explain(answers, refbooks, verdict, AS_OF)


def dividends(**overrides):
    # Всё для конвенции на месте, кроме самого сертификата: только так
    # альтернатива «а если бы он был» отвечает на заданный вопрос, а не
    # на смесь из нескольких недостающих ответов.
    return build(**{"S2.3": "RU", "S5.1": DIVIDENDS,
                    "S5.8": {"share_pct": 70, "position": "pp5_15pct",
                             "position_basis": BASIS},
                    "S7.2": "no", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
                    **overrides})


# ── Форматирование чисел ───────────────────────────────────────────────────

def test_money_uses_non_breaking_spaces():
    """Разряды не должны разрываться переносом строки в печати."""
    assert money(1_050_000) == f"1{NBSP}050{NBSP}000"
    assert money(None) == "—"


def test_percent_keeps_fractional_rates():
    """12,5 % Пакистана нельзя округлять до 13 % ради красоты."""
    assert percent(0.15) == f"15{NBSP}%"
    assert percent(0.125) == f"12,5{NBSP}%"
    assert percent(None) == "—"


# ── Трассировка ────────────────────────────────────────────────────────────

def test_every_decision_in_the_journal_gets_a_text():
    """Развилка без текста оставила бы дыру в объяснении."""
    _, verdict, e = dividends()

    assert {d.rule_id for d in e.decisions} == set(verdict.decisions)
    assert all(d.text and "текст не заведён" not in d.text for d in e.decisions)


def test_decisions_are_split_by_outcome():
    _, verdict, e = dividends()

    assert all(d.applied for d in e.applied)
    assert not any(d.applied for d in e.not_applied)
    assert len(e.decisions) == len(verdict.decisions)


def test_each_decision_points_at_the_answers_it_rests_on():
    """«Почему так» должно вести к конкретному ответу, а не к общей норме."""
    _, _, e = dividends()
    convention = next(d for d in e.decisions if d.rule_id == "R-CONV-05")

    assert [i.key for i in convention.inputs] == ["S7.3"]
    assert isinstance(convention.inputs[0], Input)
    assert convention.norms                      # нормы для кнопки «текст статьи»


def test_placeholders_are_all_substituted():
    """Незакрытая фигурная скобка в документе для подшивки недопустима."""
    _, _, e = build(**{"S2.3": "DE", "S5.1": DIVIDENDS,
                       "S5.8": {"share_pct": 10}, "S7.2": "yes", "S7.3": "yes",
                       "S7.4": "no", "S7.5": "yes", "S7.6": "no"})

    for decision in e.decisions:
        assert "{" not in decision.subject, decision.rule_id
        assert "{" not in decision.text, decision.rule_id


def test_country_is_put_in_the_instrumental_case():
    """«Конвенция с Германия» — не текст для налогового регистра."""
    _, _, e = build(**{"S2.3": "DE", "S5.1": DIVIDENDS,
                       "S5.8": {"share_pct": 10}, "S7.2": "yes", "S7.3": "yes",
                       "S7.4": "no", "S7.5": "yes", "S7.6": "no"})
    subjects = " | ".join(d.subject for d in e.decisions)

    assert "с Германией" in subjects
    assert "с Германия" not in subjects


# ── Альтернатива ───────────────────────────────────────────────────────────

def test_counterfactual_appears_only_where_the_amount_changes():
    """Второе условие: альтернатива, не меняющая ни тенге, не показывается."""
    _, _, e = dividends()

    for decision in e.decisions:
        if decision.counterfactual is None:
            continue
        assert isinstance(decision.counterfactual, Counterfactual)
        assert decision.counterfactual.delta_kzt != 0


def test_certificate_alternative_shows_the_real_saving():
    """Дивиденды RU: 15 % кодекса против 10 % конвенции — разница 350 000 ₸."""
    _, verdict, e = dividends()
    convention = next(d for d in e.decisions if d.rule_id == "R-CONV-05")

    assert verdict.kpn.amount_kzt == 1_050_000
    assert convention.applied is False
    assert convention.counterfactual is not None
    assert convention.counterfactual.kpn_amount_kzt == 700_000
    assert convention.counterfactual.delta_kzt == -350_000
    assert "меньше" in convention.counterfactual.display


def test_applied_decisions_carry_no_alternative():
    """У применившейся ветки альтернативы нет: она и есть то, что произошло."""
    _, _, e = dividends()

    assert all(d.counterfactual is None for d in e.applied)


def test_alternative_is_silent_when_it_changes_nothing():
    """Сертификат у страны без конвенции суммы не меняет — строки нет."""
    _, _, e = build(**{"S2.3": "OFF54", "S5.1": "services",
                       "S5.5": "consulting", "S6.1": "outside_kz",
                       "S7.2": "no"})
    for decision in e.decisions:
        assert decision.counterfactual is None


# ── Расчёт ─────────────────────────────────────────────────────────────────

def test_calc_lines_end_at_the_verdict_amount():
    """Последняя строка расчёта обязана совпадать с суммой в вердикте:
    расхождение здесь означает, что объяснение описывает другой расчёт."""
    _, verdict, e = dividends()
    kpn_line = next(c for c in e.calc if c.label.startswith("КПН"))

    assert kpn_line.value_kzt == verdict.kpn.amount_kzt
    assert money(verdict.kpn.amount_kzt) in kpn_line.value


def test_no_calc_lines_for_an_undetermined_obligation():
    """Спор не разрешён — числа нет ни в вердикте, ни в расчёте."""
    _, verdict, e = dividends(**{"S5.8": {"share_pct": 70}})

    assert verdict.kpn.rate is None
    assert not [c for c in e.calc if c.label.startswith("КПН")]


def test_currency_case_shows_the_rate_that_was_used():
    _, verdict, e = build(**{"S2.3": "NL", "S5.1": "transport_intl",
                             "S1.5": "EUR", "S4.4": 7_000.0, "S4.5": 591.0,
                             "S7.2": "no"})
    rates = [c for c in e.calc if "Курс" in c.label]

    assert rates and rates[0].value == "591,00"
    assert verdict.kpn.base_kzt == 4_137_000


def test_explanation_is_deterministic():
    """Тот же набор ответов — то же объяснение. Иначе документ невоспроизводим."""
    first = [(d.rule_id, d.text) for d in dividends()[2].decisions]
    second = [(d.rule_id, d.text) for d in dividends()[2].decisions]

    assert first == second


def test_explain_does_not_mutate_answers():
    """Альтернатива считается на копии: подмена ответа пользователя ради
    контрфакта испортила бы и вердикт, и черновик."""
    answers, _, _ = dividends()
    before = repr(answers)
    refbooks = get_rules()
    verdict = evaluate(answers, refbooks=refbooks, as_of_date=AS_OF)
    explain(answers, refbooks, verdict, AS_OF)

    assert repr(answers) == before


def test_decision_dataclass_shape_is_stable():
    """Контракт для интерфейса: поля, на которые опирается блок 2."""
    _, _, e = dividends()
    decision = e.decisions[0]

    assert isinstance(decision, Decision)
    for attribute in ("rule_id", "subject", "applied", "text", "norms",
                      "inputs", "note", "counterfactual"):
        assert hasattr(decision, attribute), attribute
