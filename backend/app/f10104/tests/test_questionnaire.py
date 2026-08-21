"""Периметр анкеты: что спрашиваем, а что только заполняем.

Правило, ради которого написан файл: в анкете спрашивается ПРИЗНАК, от
которого зависит вывод; реквизит, нужный только для заполнения графы формы,
спрашивается на этапе выгрузки. Пока файл формы не выдаётся — не спрашивается
вовсе.

Здесь оно проверяется с той стороны, с которой ломается: не «поле убрано
из визарда» (это TypeScript, тесты его не видят), а «расчёт не зависит от
того, введён реквизит или нет». Если завтра кто-то привяжет к наименованию
контрагента хоть одну цифру, тест упадёт, и поле придётся возвращать
в анкету осознанно.
"""
from dataclasses import asdict
from datetime import date

import pytest

from app.f10104.engine import FILLED_BY_USER, evaluate
from app.f10104.rules import get_rules

from .answers import OUTSIDE_KZ, base

COUNTERPARTY = {
    "name": "Shenzhen Trading Co., Ltd",
    "tin": "91440300MA5EX1234K",
    "contract_no": "SZ-2026/14",
}


def run(**over):
    answers = base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S1.4": "yes", "S1.5": "USD",
        "S2.3": "CN", "S5.1": "services", "S5.2": "yes", "S5.3": "yes",
        "S5.5": "consulting", "S6.1": "kz", "S7.2": "no",
        "S4.1": date(2026, 2, 20), "S4.2": date(2026, 3, 10),
        "S4.4": 110000.0, "S4.5": 500.0,
        # Реквизиты контрагента визард больше не спрашивает — значит и здесь
        # их по умолчанию нет. base() отдаёт их для старых тестов.
        "S2.4": {}, **over,
    })
    return evaluate(answers, refbooks=get_rules(), as_of_date=date(2026, 6, 30))


# ── Реквизиты контрагента: сквозные, на вывод не влияют ────────────────────

def test_counterparty_details_change_nothing_but_the_graphs():
    """Наименование, налоговый номер и реквизиты контракта — сквозные.

    Сравниваются два вердикта целиком, без раздела graphs: если различий нет,
    значит спрашивать эти три поля в анкете незачем — помогайка возвращала бы
    пользователю то, что он сам ввёл.
    """
    with_details = asdict(run(**{"S2.4": dict(COUNTERPARTY)}))
    without = asdict(run())

    with_details.pop("graphs"), without.pop("graphs")
    assert with_details == without


@pytest.mark.parametrize("graph", ["C", "E", "G"])
def test_graphs_say_who_fills_them_when_details_are_not_asked(graph):
    """В заготовке графа не пустая: сказано, что её заполняет пользователь.

    Пустая клетка читается как «здесь ничего не нужно», и форма уходит
    в налоговую без наименования контрагента.
    """
    assert run().graphs[graph] == FILLED_BY_USER


@pytest.mark.parametrize("graph,key", [("C", "name"), ("E", "tin"),
                                       ("G", "contract_no")])
def test_graphs_carry_details_when_they_are_known(graph, key):
    """А если реквизиты пришли — они и подставляются, без «заполняете вы»."""
    v = run(**{"S2.4": dict(COUNTERPARTY)})
    assert v.graphs[graph] == COUNTERPARTY[key]


# ── УНК: признак вместо номера ─────────────────────────────────────────────

@pytest.mark.parametrize("answer,expected", [
    ("yes", True),
    ("no", False),
    (None, False),
    ("", False),
    ("УНК-9", True),        # старый черновик с номером — правило не теряется
])
def test_currency_contract_is_a_yes_or_no_fact(answer, expected):
    """Для R-REP-02 важен факт постановки на учёт, а не сам номер.

    Старая форма ответа (введённый номер) продолжает работать: черновики,
    сохранённые до укорочения анкеты, не должны молча остаться без правила.

    Правило работает на необлагаемых суммах: облагаемый доход попадает
    в форму по R-REP-01 независимо от валютного договора.
    """
    v = run(**{"S5.1": "services", "S5.5": "software_support",
               "S6.1": OUTSIDE_KZ, "S2.3": "DE", "S2.5": answer})
    assert v.kpn.taxable is False, "иначе проверяется не то правило"
    assert v.decisions["R-REP-02"] is expected


# ── S3.5: «не знаю» здесь законно ──────────────────────────────────────────

def flags(v):
    return set(v.flags)


def test_registration_in_kz_raises_pe_risk():
    """Зарегистрирован в налоговых органах РК — это признак ПУ, не реквизит."""
    v = run(**{"S3.5": "yes"})
    assert "F-PE-RISK" in flags(v)
    assert v.decisions["pe-risk"] is True


def test_unknown_registration_is_neither_yes_nor_no():
    """«Не знаю» — не «нет».

    Это свойство контрагента, а не осведомлённости бухгалтера: проверить его
    самому он может не всегда. Молча приравнять к «нет» значит скрыть риск
    постоянного учреждения, поэтому поднимается отдельный флаг.
    """
    v = run(**{"S3.5": "unknown"})
    assert "F-PE-UNKNOWN" in flags(v)
    assert "F-PE-RISK" not in flags(v)
    assert v.decisions["pe-risk"] is False


def test_no_answer_raises_nothing():
    """Вопрос не задан — флага нет. Иначе он сработает у всех и его перестанут читать."""
    assert flags(run()) & {"F-PE-RISK", "F-PE-UNKNOWN"} == set()


# ── Подсказки и памятка живут в справочнике ────────────────────────────────

@pytest.mark.parametrize("question", ["S1.4", "S2.5", "S3.5"])
def test_question_hint_exists_and_says_where_to_look(question):
    hint = get_rules()["question_hints"][question]
    assert len(hint) > 60, "подсказка должна говорить, где посмотреть ответ"


def test_vat_registration_hint_does_not_hint_the_answer():
    """Подсказка объясняет, где проверить статус, а не решает за пользователя."""
    hint = get_rules()["question_hints"]["S1.4"]
    assert "кабинете налогоплательщика" in hint


def test_cert_memo_reads_without_the_wizard():
    """Памятку отправляют нерезиденту — в ней не может быть слов о расчёте.

    Проверяются именно отсылки к контексту («ваш расчёт», «вы ответили»),
    а не любое употребление слова «вы»: памятка обращается к читателю
    и должна это делать.
    """
    memo = get_rules()["cert_memo"]
    assert memo["title"]
    assert len(memo["sections"]) >= 5

    text = " ".join(
        " ".join(filter(None, [s.get("heading"), s.get("lead"), s.get("note"),
                               s.get("basis"), *(s.get("items") or [])]))
        for s in memo["sections"]
    ).lower()

    for context_word in ["ваш расчёт", "вы ответили", "по вашим ответам",
                         "помогайк", "визард"]:
        assert context_word not in text, context_word

    # Две даты, которые путают чаще всего, обязаны быть обе.
    assert "31 марта" in text and "705" in text


def test_cert_memo_does_not_touch_the_calculation():
    """Памятка справочная: ответы шага S8 в расчёт не входят.

    Шаг убран из визарда, но старые черновики с его ответами существуют.
    Вердикт по ним обязан совпасть с вердиктом без них.
    """
    stale = {"S8.1": "yes", "S8.2": "yes", "S8.3": "no", "S8.7": "yes"}
    assert asdict(run(**stale)) == asdict(run())
