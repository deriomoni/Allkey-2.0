"""F-CERT-DEADLINE — напоминание о сроке ст. 705 п. 3, суженное до смысла.

Довод по существу верен: срок представления документа важен именно тогда,
когда документа нет. Но в широком виде флаг встаёт почти на каждой операции,
а флаг, срабатывающий всегда, к третьему экрану перестают читать — вместе
со всеми остальными. То же самое происходит с красным цветом, когда его
слишком много.

Поэтому четыре условия, и все вместе:

  1. с этой страной есть конвенция и она не офшор;
  2. документа нет либо он не отвечает ст. 702;
  3. годный документ дал бы МЕНЬШИЙ налог;
  4. срок ст. 705 п. 3 ещё не истёк — 31 марта года, следующего за годом
     выплаты, не прошло.

И отдельно: при признаках постоянного учреждения флаг гасится совсем.
"""
from datetime import date

from app.f10104.engine import evaluate
from app.f10104.rules import get_rules

from .answers import base

BEFORE_DEADLINE = date(2026, 6, 30)
AFTER_DEADLINE = date(2027, 6, 30)


def run(on=BEFORE_DEADLINE, **over):
    answers = base(**{
        "S1.5": "USD", "S4.1": date(2026, 2, 20), "S4.2": date(2026, 3, 10),
        "S4.4": 10000.0, "S4.5": 500.0, "S7.2": "no", "S7.3": None, **over,
    })
    return evaluate(answers, refbooks=get_rules(), as_of_date=on)


def raised(verdict) -> bool:
    return "F-CERT-DEADLINE" in verdict.flags


def test_raised_when_the_document_would_actually_save_money():
    """Германия, услуги: с документом конвенция освобождает полностью,
    без него — 20 %. Здесь напоминание стоит своих строк."""
    v = run(**{"S2.3": "DE"})

    assert v.kpn.rate == 0.20
    assert raised(v)


def test_silent_for_an_offshore_where_no_convention_exists():
    """Ст. 682 п. 2: к офшорным юрисдикциям конвенция не применяется вовсе.
    Сертификат не спасёт ничего, и говорить о его сроке незачем."""
    v = run(**{"S2.3": "OFF54", "S5.1": "rent", "S5.5": "rent_vehicle"})

    assert not raised(v)


def test_silent_when_the_convention_would_not_lower_the_rate():
    """Пакистан, роялти: и кодекс, и договор дают 15 %. Документ ничего
    не меняет — напоминание было бы обещанием экономии, которой нет."""
    v = run(**{"S2.3": "PK", "S5.1": "royalty", "S7.5": "yes"})

    assert v.kpn.rate == 0.15
    assert not raised(v)


def test_silent_after_the_article_705_deadline_has_passed():
    """Документ представляется не позднее 31 марта года, следующего за годом
    выплаты. Срок прошёл — собирать поздно, напоминание становится шумом."""
    before = run(on=BEFORE_DEADLINE, **{"S2.3": "DE"})
    after = run(on=AFTER_DEADLINE, **{"S2.3": "DE"})

    assert raised(before)
    assert not raised(after)


def test_permanent_establishment_silences_it_completely():
    """Признаки ПУ — один стоп-сигнал вместо двух разнонаправленных подсказок.

    Если ПУ образовалось, вся конструкция «удержали у источника и применили
    конвенцию» под вопросом, и совет собирать сертификат уводит бухгалтера
    от настоящей проблемы.
    """
    v = run(**{"S2.3": "TR", "S3.4": "construction", "S6.1": "kz"})

    assert "F-PE-RISK" in v.flags
    assert not raised(v)


def test_the_saving_is_measured_by_the_real_branch_not_a_copy():
    """Проверка «спасёт ли документ» обязана идти той же веткой, что и расчёт.

    Отдельный предикат однажды разойдётся с настоящей веткой, и помогайка
    начнёт обещать экономию, которой в расчёте нет. Здесь это видно так:
    при неподтверждённом окончательном получателе (S7.5) конвенция не
    применится даже с документом — значит и флага быть не должно.
    """
    without_beneficiary = run(**{"S2.3": "RU", "S5.1": "royalty", "S7.5": "no"})
    with_beneficiary = run(**{"S2.3": "RU", "S5.1": "royalty", "S7.5": "yes"})

    assert not raised(without_beneficiary)
    assert raised(with_beneficiary)


def test_the_dry_run_leaves_no_trace_in_the_verdict():
    """Холостой прогон ветки не должен добавлять ни флагов, ни развилок,
    ни строк обоснования: он существует только чтобы получить процент."""
    v = run(**{"S2.3": "DE"})

    assert v.kpn.convention_applied is not True
    assert "R-CONV-04" not in v.decisions
    assert not any("освобождение от налогообложения" in b for b in v.kpn.basis)
