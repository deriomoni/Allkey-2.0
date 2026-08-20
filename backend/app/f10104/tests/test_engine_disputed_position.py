"""Разрешение спорной ставки по дивидендам самим пользователем.

Механизм узкий намеренно: это не «переопредели ставку», а «я получил
заключение по конкретному вопросу». Четыре ограничения из справочника
(`kpn_rates.dividends_25.user_resolution`) проверяются здесь по одному.
"""
from datetime import date

import pytest

from app.f10104.engine import EngineError
from app.f10104.rules import get_rules

from .answers import base, DIVIDENDS

BASIS = "письмо КГД № 123 от 01.02.2026"


def run(share_answer: dict, amount: float = 7_000_000.0):
    from app.f10104.engine import evaluate  # noqa: PLC0415

    return evaluate(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "RU", "S5.1": DIVIDENDS,
        "S5.8": share_answer, "S1.5": "KZT", "S7.2": "no",
        "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": amount, "S4.5": 1.0,
    }), refbooks=get_rules(), as_of_date=date(2026, 3, 31))


def test_default_is_no_choice_and_no_number():
    """Предвыбранного значения нет и быть не может: предвыбор превратил бы
    спорный вопрос обратно в позицию помогайки, только неявную."""
    v = run({"share_pct": 70})

    assert v.kpn.position_chosen is None
    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert "F-DIV-25" in v.flags
    assert "F-DIV-25-RESOLVED" not in v.flags


def test_choice_without_basis_is_not_accepted():
    """Без обоснования механизм стал бы способом получить нужное число одним
    кликом. Выбор игнорируется, вывод остаётся неопределённым."""
    v = run({"share_pct": 70, "position": "pp5_15pct"})

    assert v.kpn.position_chosen is None
    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert "F-DIV-25" in v.flags
    assert any("обоснование не" in b for b in v.kpn.basis)


def test_choice_with_basis_resolves_the_rate():
    v = run({"share_pct": 70, "position": "pp5_15pct", "position_basis": BASIS})

    assert v.kpn.rate == 0.15
    assert v.kpn.amount_kzt == 1_050_000
    assert v.kpn.position_chosen == "pp5_15pct"
    assert v.kpn.position_basis == BASIS
    assert any(BASIS in b for b in v.kpn.basis)      # уходит в обоснование расчёта


def test_the_other_position_gives_the_other_number():
    """Цена вопроса на этой сумме — 700 000 ₸ разницы."""
    pp5 = run({"share_pct": 70, "position": "pp5_15pct", "position_basis": BASIS})
    pp6 = run({"share_pct": 70, "position": "pp6_5pct", "position_basis": BASIS})

    assert (pp5.kpn.amount_kzt, pp6.kpn.amount_kzt) == (1_050_000, 350_000)
    assert pp5.kpn.amount_kzt - pp6.kpn.amount_kzt == 700_000


def test_flag_does_not_go_out_after_the_choice():
    """Вопрос остаётся спорным, просто позиция определена: флаг меняется
    на подтверждающий и понижается до info, но не исчезает."""
    v = run({"share_pct": 70, "position": "pp6_5pct", "position_basis": BASIS})

    assert "F-DIV-25-RESOLVED" in v.flags
    assert v.flag_severity("F-DIV-25-RESOLVED") == "info"
    assert v.confidence != "manual_review"           # вывод определён


def test_progressive_scale_of_subparagraph_6():
    """Подпункт 6): 5 % в пределах 230 000 МРП, свыше — налог с порога плюс
    15 % с превышения. Порог 230 000 × 4 325 = 994 750 000 ₸.

    База 1 200 000 000 ₸ → 994 750 000 × 5 % + 205 250 000 × 15 %
                         = 49 737 500 + 30 787 500 = 80 525 000 ₸.
    """
    v = run({"share_pct": 70, "position": "pp6_5pct", "position_basis": BASIS},
            amount=1_200_000_000.0)

    assert v.kpn.amount_kzt == 80_525_000


def test_below_the_progressive_threshold_the_rate_is_flat():
    v = run({"share_pct": 70, "position": "pp6_5pct", "position_basis": BASIS},
            amount=100_000_000.0)

    assert v.kpn.amount_kzt == 5_000_000            # ровно 5 %


def test_unknown_position_is_rejected_loudly():
    with pytest.raises(EngineError, match="Неизвестная позиция"):
        run({"share_pct": 70, "position": "pp7_0pct", "position_basis": BASIS})


def test_mechanism_does_not_touch_other_disputed_cases():
    """Выбор действует только на эту развилку. Нидерланды дают manual_review
    по другой причине — неоднозначная запись договорной ставки, — и позиция
    по дивидендам кодекса её не разрешает."""
    from app.f10104.engine import evaluate  # noqa: PLC0415

    v = evaluate(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "NL", "S5.1": DIVIDENDS,
        "S5.8": {"share_pct": 10, "position": "pp5_15pct", "position_basis": BASIS},
        "S1.5": "KZT", "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 7_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
    }), refbooks=get_rules(), as_of_date=date(2026, 3, 31))

    assert v.kpn.rate is None
    assert v.confidence == "manual_review"


# ── Порядок: сначала спор по кодексу, потом потолок конвенции ──────────────
#
# R-CONV-08 (порог доли по конвенции) и спор по ст. 682 висят на одном ответе
# S5.8, но это разные нормы и разные группы правил. Порядок между ними не
# декоративный: пока ставка кодекса не определена, сравнивать с потолком
# конвенции не с чем, и договорная ставка не имеет права стать ответом сама.

def run_ru(share_answer: dict, certificate: bool):
    from app.f10104.engine import evaluate  # noqa: PLC0415

    a = {
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "RU", "S5.1": DIVIDENDS,
        "S5.8": share_answer, "S1.5": "KZT", "S4.1": date(2026, 3, 10),
        "S4.2": date(2026, 3, 20), "S4.4": 7_000_000.0, "S4.5": 1.0,
    }
    a.update({"S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes",
              "S7.6": "no"} if certificate else {"S7.2": "no"})
    return evaluate(base(**a), refbooks=get_rules(), as_of_date=date(2026, 3, 31))


def test_treaty_cannot_answer_an_unresolved_dispute():
    """Сертификат резидентства спор по кодексу не снимает.

    Под потолком конвенции остаются обе позиции кодекса — 5 % и 15 %, — а
    значит и результат остаётся неопределённым. Если бы движок применил
    договорные 10 % как самостоятельную ставку, спорный вопрос получил бы
    ответ, которого в нормах нет.
    """
    v = run_ru({"share_pct": 70}, certificate=True)

    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0


def test_ceiling_becomes_live_once_the_dispute_is_resolved():
    """После выбора позиции сравнение с потолком снова работает — и в обе
    стороны, что и есть смысл слова «потолок».

    пп. 5) — 15 % кодекса выше договорных 10 %, применяется конвенция.
    пп. 6) —  5 % кодекса ниже договорных 10 %, применяется кодекс.
    """
    pp5 = run_ru({"share_pct": 70, "position": "pp5_15pct",
                  "position_basis": BASIS}, certificate=True)
    pp6 = run_ru({"share_pct": 70, "position": "pp6_5pct",
                  "position_basis": BASIS}, certificate=True)

    assert (pp5.kpn.rate, pp5.kpn.amount_kzt) == (0.10, 700_000)
    assert "F-TREATY-CEILING" not in pp5.flags

    assert (pp6.kpn.rate, pp6.kpn.amount_kzt) == (0.05, 350_000)
    assert "F-TREATY-CEILING" in pp6.flags


def test_r_conv_08_record_describes_the_treaty_threshold():
    """Номер разведён: R-CONV-08 — порог конвенции, не норма кодекса."""
    decisions = get_rules()["decisions"]

    assert "R-CONV-08" in decisions
    assert "R-KPN-08" not in decisions            # переехало, а не задвоилось
    assert decisions["R-CONV-08"]["fork"] == ["S5.8"]
