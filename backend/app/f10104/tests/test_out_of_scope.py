"""Явные выходы за периметр: там, где помогайка не считает.

Принцип из ТЗ §5а: помогайка считает там, где вывод следует из анкеты. Где он
зависит от первичных документов или квалификации отношений — не считает и не
гадает, а показывает выход. Один уверенный неверный ответ обесценивает сто
верных.

Здесь проверяется ровно одно: по этим веткам не возвращается НИ ОДНОЙ суммы —
ни базы, ни налога, ни ставки, ни кода дохода, ни срока. Серая предварительная
цифра здесь была бы хуже её отсутствия: её запомнят, а оговорку рядом нет.
"""
from datetime import date

import pytest

from app.f10104.engine import aggregate_form, evaluate
from app.f10104.rules import get_rules

from .answers import base

OUT_OF_SCOPE_INCOME = ["goods", "agency", "inbound_aid"]


def run(income: str, **over):
    answers = base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S1.4": "yes", "S1.5": "USD",
        "S2.3": "CN", "S5.1": income, "S5.2": "yes", "S5.3": "yes",
        "S5.4": "yes", "S5.4a": 10000.0, "S5.5": "install", "S6.1": "kz",
        "S7.2": "no", "S4.1": date(2026, 2, 20), "S4.2": date(2026, 3, 10),
        "S4.4": 110000.0, "S4.5": 500.0, "S2.5": "УНК-9", **over,
    })
    return evaluate(answers, refbooks=get_rules(), as_of_date=date(2026, 6, 30))


# ── Ни одной суммы ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("income", OUT_OF_SCOPE_INCOME)
def test_not_a_single_amount_comes_back(income):
    """Ни базы, ни налога, ни ставки — ни в каком виде."""
    v = run(income)

    assert v.route == "out_of_scope"
    assert v.out_of_scope == {"goods": "goods", "agency": "agency",
                              "inbound_aid": "inbound_aid"}[income]
    assert v.kpn.base_kzt == 0
    assert v.kpn.amount_kzt == 0
    assert v.kpn.rate is None
    assert v.kpn.taxable is False
    assert v.vat.base_kzt in (0, None)
    assert v.vat.amount_kzt in (0, None)


@pytest.mark.parametrize("income", OUT_OF_SCOPE_INCOME)
def test_no_income_code_and_no_form_graphs(income):
    """Код вида дохода — это уже ответ. Его тоже не даём."""
    v = run(income)

    assert not v.graphs.get("F")
    assert not v.graphs.get("I")
    assert not v.graphs.get("J")


@pytest.mark.parametrize("income", OUT_OF_SCOPE_INCOME)
def test_no_deadlines_in_the_checklist(income):
    """У неизвестной суммы не может быть срока уплаты."""
    v = run(income)

    assert v.deadlines.kpn_payment is None
    assert v.deadlines.vat_payment is None
    assert v.deadlines.form_101_04 is None


@pytest.mark.parametrize("income", OUT_OF_SCOPE_INCOME)
def test_does_not_go_into_the_form(income):
    v = run(income)

    assert v.reporting.form_101_04_required is False
    assert v.reporting.reported_in_form is False


def test_does_not_go_into_the_quarterly_total():
    """Операция за периметром не складывается в строки 101.04.001 и 002.

    Ноль в сумме читался бы как «посчитали и получилось ноль» — а мы
    не считали вовсе.
    """
    ordinary = evaluate(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S1.4": "yes", "S1.5": "USD",
        "S2.3": "DE", "S5.1": "services", "S5.5": "consulting",
        "S6.1": "outside", "S7.2": "no", "S4.1": date(2026, 2, 20),
        "S4.2": date(2026, 3, 10), "S4.4": 10000.0, "S4.5": 500.0,
    }), refbooks=get_rules(), as_of_date=date(2026, 6, 30))

    alone = aggregate_form([ordinary])
    with_goods = aggregate_form([ordinary, run("goods")])

    assert alone.line_001 == with_goods.line_001
    assert alone.line_002 == with_goods.line_002
    assert with_goods.line_002["IV"] == ordinary.kpn.amount_kzt


# ── Тексты живут в справочнике ─────────────────────────────────────────────

@pytest.mark.parametrize("key", ["goods", "agency", "inbound_aid"])
def test_the_exit_screen_texts_come_from_the_refbook(key):
    """В TypeScript этих формулировок быть не должно — они здесь."""
    block = get_rules()["out_of_scope"][key]

    assert block["title"] and block["lead"] and block["what_to_do"]


def test_goods_names_all_four_forks_with_their_norms():
    """Экран выхода обязан назвать конкретные развилки, а не сказать
    «сложный случай»: иначе он неотличим от отказа без объяснения."""
    forks = get_rules()["out_of_scope"]["goods"]["forks"]

    assert len(forks) == 4
    for fork in forks:
        assert fork["q"].endswith("?")
        assert fork["a"]
        assert fork["norms"], fork["q"]      # у каждой развилки своя норма

    # `norms` — строка со списком норм через точку с запятой; список тоже
    # принимаем, чтобы сторож не сломался при смене формы хранения.
    joined = " ".join(f["norms"] if isinstance(f["norms"], str)
                      else " ".join(f["norms"]) for f in forks)
    for norm in ("680", "679"):
        assert norm in joined, joined


def test_the_variant_is_not_removed_from_the_list():
    """Убирать вариант нельзя: не нашедший своего случая выберет соседний
    и получит уверенный неверный ответ — хуже честного отказа.

    Сторож на само правило: оно записано в справочнике и должно там остаться.
    """
    rules = get_rules()["out_of_scope"]["_rules"]

    assert any("остаётся в списке" in r for r in rules)
    assert any("уверенный неверный" in r for r in rules)


# ── Дисклеймер экрана выхода ───────────────────────────────────────────────

def test_the_exit_screen_has_its_own_disclaimer():
    """Общий дисклеймер начинается со слов «помогайка формирует расчёт» —
    на экране, где расчёта нет, это читается несогласованно. Переписывать
    общий под два разных экрана значило бы ослабить его для обоих, поэтому
    у выхода свой текст."""
    block = get_rules()["disclaimer"]
    general, exit_text = block["text"], block.get("out_of_scope_text")

    assert exit_text, "текст дисклеймера для экрана выхода не заведён"
    assert exit_text != general
    assert "не считает налог" in exit_text
    assert "не налоговая консультация" in exit_text


def test_the_exit_disclaimer_is_stamped_with_the_refbook_version():
    """Он тоже уходит в бумагу, значит обязан назвать редакцию справочника."""
    from app.f10104.router import _disclaimer  # noqa: PLC0415

    rules = get_rules()
    built = _disclaimer()["out_of_scope_text"]

    assert "{" not in built, "плейсхолдер не подставлен"
    assert rules["meta"]["rules_version"] in built
    assert rules["meta"]["generated"] in built


def test_the_placement_rule_for_the_exit_text_is_written_down():
    """Когда какой текст показывать — правило в справочнике, а не в коде."""
    rules = " ".join(str(r) for r in get_rules()["disclaimer"]["placement_rules"])

    assert "out_of_scope" in rules or "выход" in rules.lower()
