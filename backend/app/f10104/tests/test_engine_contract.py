"""Контракт движка — железные правила задания, а не налоговые нормы.

Проверяется то, что делает вывод воспроизводимым: чистота функции, отсутствие
побочных эффектов и штамп версии правил. Эти свойства ломаются тихо, поэтому
их держим тестами наравне с расчётом.

"""
from datetime import date

from app.f10104.rules import get_rules, rules_version

from .answers import base, OUTSIDE_KZ, SERVICES


def run(answers: dict, on: date = date(2026, 9, 30)):
    from app.f10104.engine import evaluate  # noqa: PLC0415 — см. комментарий выше

    return evaluate(answers, refbooks=get_rules(), as_of_date=on)


def test_engine_is_deterministic():
    """Один и тот же вход всегда даёт один и тот же выход (правило 3)."""
    answers = base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                      "S6.1": OUTSIDE_KZ, "S4.4": 10000.0, "S4.5": 500.0})

    assert run(answers) == run(answers)


def test_engine_does_not_mutate_answers():
    """Побочных эффектов нет — входной словарь остаётся нетронутым."""
    answers = base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                      "S6.1": OUTSIDE_KZ, "S4.4": 10000.0, "S4.5": 500.0})
    snapshot = dict(answers)

    run(answers)

    assert answers == snapshot


def test_verdict_carries_rules_version():
    """Версия справочника фиксируется в вердикте — иначе вывод не
    воспроизвести через год (правило 5)."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": OUTSIDE_KZ, "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.rules_version == rules_version()


def test_R_ROUTE_01_period_before_2026_is_out_of_scope():
    """Периоды до 2026 года вне периметра v1: действовал старый кодекс."""
    v = run(base(**{"S1.1": {"quarter": 4, "year": 2025}, "S2.3": "DE",
                    "S5.1": SERVICES, "S5.5": "consulting", "S6.1": OUTSIDE_KZ}),
            on=date(2025, 12, 31))

    assert v.route == "out_of_scope"
    assert v.reporting.form_101_04_required is False


def test_confidence_levels_are_from_the_allowed_set():
    """Три уровня уверенности и никаких других (правило 7)."""
    v = run(base(**{"S2.3": "DE", "S5.1": SERVICES, "S5.5": "consulting",
                    "S6.1": OUTSIDE_KZ, "S4.4": 10000.0, "S4.5": 500.0}))

    assert v.confidence in {"confirmed", "likely", "manual_review"}
