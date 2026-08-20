"""Ставки по конвенциям об избежании двойного налогообложения.

Источник — справочная таблица ИС «Параграф» doc_id 37913498 на 01.01.2026,
перенесённая в `conventions.rates` справочника правил. Источник вторичный:
это сводка консультанта, а не текст конвенции, поэтому каждая применённая
ставка сопровождается флагом `F-TREATY-RATE`, а неоднозначные записи чисел
не дают вовсе.
"""
from datetime import date

from app.f10104.rules import get_rules

from .answers import base, DIVIDENDS, INTEREST, OUTSIDE_KZ, ROYALTY, SERVICES


def run(answers: dict):
    from app.f10104.engine import evaluate  # noqa: PLC0415

    return evaluate(answers, refbooks=get_rules(), as_of_date=date(2026, 3, 31))


def dividends(country: str, share: int, **over) -> dict:
    """Дивиденды с полностью выполненными условиями ст. 706, если не сказано иное."""
    return base(**{
        "S1.1": {"quarter": 1, "year": 2026},
        "S2.3": country, "S5.1": DIVIDENDS, "S5.8": {"share_pct": share},
        "S1.5": "KZT", "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 7_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
        **over,
    })


# ── Золотой кейс по России: две ветки ─────────────────────────────────────

# ВАЖНО о доле участия в этих тестах. С редакции 1.5.0 доля 25 % и выше
# переводит ставку в спорную: подпункт 5) ст. 682 прямо исключает доходы
# подпункта 6), и движок вывод не даёт. Поэтому проверки договорных ставок
# ведутся на доле НИЖЕ порога — там ставка кодекса определена, и видно, что
# именно делает конвенция. Спорная ветка проверяется отдельно ниже.

def test_russia_dividends_without_certificate_stays_on_tax_code():
    """Сертификата нет — конвенция не применяется, ставка Налогового кодекса."""
    v = run(dividends("RU", 10, **{"S7.2": "no", "S7.3": "no"}))

    assert v.kpn.convention_applied is False
    assert v.kpn.rate == 0.15
    assert v.kpn.amount_kzt == 1_050_000
    # Доля 10 % — ниже порога спорности, F-DIV-25 не поднимается.
    assert "F-DIV-25" not in v.flags
    assert "F-TREATY-RATE" not in v.flags


def test_russia_dividends_with_certificate_uses_treaty_rate():
    """Сертификат есть, условия ст. 706 выполнены — 10 % по конвенции с Россией.
    Контрольный результат 1 050 000 ₸ верен только без применения конвенции."""
    v = run(dividends("RU", 10))

    assert v.kpn.convention_applied is True
    assert v.kpn.convention_type == "reduced"
    assert v.kpn.rate == 0.10
    assert v.kpn.amount_kzt == 700_000
    assert "F-TREATY-RATE" in v.flags     # ставка предельная и из вторичного источника
    assert "F-MLI" in v.flags             # у конвенции с Россией MLI есть


def test_two_branches_differ():
    """Если обе ветки дают одно и то же — конвенция не подключена к расчёту."""
    without = run(dividends("RU", 10, **{"S7.2": "no", "S7.3": "no"}))
    with_cert = run(dividends("RU", 10))

    assert without.kpn.amount_kzt != with_cert.kpn.amount_kzt
    assert (without.kpn.amount_kzt, with_cert.kpn.amount_kzt) == (1_050_000, 700_000)


# ── Порог доли участия ────────────────────────────────────────────────────

def test_treaty_reduced_rate_is_unreachable_while_the_code_rate_is_disputed():
    """Пониженная ставка Германии требует доли от 25 % — но ровно с этой доли
    спорна сама ставка кодекса, и конвенция этого не лечит: она потолок, а под
    потолком остаются обе позиции (5 % по пп. 6) и 15 % по пп. 5)).

    Поэтому вывод не даётся вовсе. Это не дефект: пока не решён вопрос
    подпунктов 5) и 6), договорная ставка ни к чему не применяется."""
    v = run(dividends("DE", 30))

    assert v.kpn.applicable is None
    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert "F-DIV-25" in v.flags


def test_germany_dividends_default_rate_below_ownership_threshold():
    v = run(dividends("DE", 10))

    assert v.kpn.rate == 0.15
    assert v.kpn.amount_kzt == 1_050_000


def test_flat_rate_when_no_ownership_threshold():
    """У России порога нет — ставка одна и та же при любой доле."""
    assert run(dividends("RU", 5)).kpn.rate == run(dividends("RU", 20)).kpn.rate == 0.10


# ── Шесть стран, где таблица чисел не даёт ────────────────────────────────

def test_netherlands_dividends_give_no_number():
    """Нидерланды: три ступени и условие нулевой ставки требует проверки.
    Работает уровень обязательства: цифры нет ни в каком виде."""
    v = run(dividends("NL", 10))

    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert v.kpn.rate_undetermined is True
    assert v.kpn.treaty_note                     # вместо числа — что проверить
    assert v.confidence == "manual_review"
    assert v.graphs["I"] is None                 # графа I пустая, не ноль


def test_slovakia_contradiction_is_preserved_not_fixed():
    """По Словакии в источнике прямая нестыковка: «1) 10 % / 30 2) 5 %» —
    пониженная ставка выше обычной. Она зафиксирована как есть, а не
    «исправлена» на правдоподобную."""
    v = run(dividends("SK", 10))

    assert v.kpn.rate is None
    assert v.kpn.rate_undetermined is True
    assert "противоречив" in v.kpn.treaty_note or "нестыковк" in v.kpn.treaty_note


def test_all_six_manual_review_countries_give_no_number():
    for iso in ("NL", "SK", "AE", "IE", "HR", "CY"):
        v = run(dividends(iso, 10))
        assert v.kpn.rate is None, f"{iso}: ставка не должна определяться"
        assert v.kpn.amount_kzt == 0, f"{iso}: суммы быть не должно"
        assert v.confidence == "manual_review", iso


# ── Роялти и вознаграждения ───────────────────────────────────────────────

def test_royalty_uses_treaty_rate():
    v = run(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "RU", "S5.1": ROYALTY,
        "S5.6": "no", "S1.5": "KZT", "S4.1": date(2026, 3, 10),
        "S4.2": date(2026, 3, 20), "S4.4": 1_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
    }))

    assert v.kpn.rate == 0.10                     # по НК было бы 15 %
    assert v.kpn.amount_kzt == 100_000
    assert "F-TREATY-RATE" in v.flags


def test_interest_uses_treaty_rate():
    v = run(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "RU", "S5.1": INTEREST,
        "S1.5": "KZT", "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 1_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
    }))

    assert v.kpn.rate == 0.10                     # по НК 10 % и по конвенции 10 %
    assert "F-TREATY-RATE" in v.flags


# ── Услуги освобождением, а не ставкой ────────────────────────────────────

def test_services_still_get_full_exemption_not_a_treaty_rate():
    """Для работ и услуг конвенция даёт полное освобождение по ст. 705,
    а не пониженную ставку: F-TREATY-RATE тут не нужен."""
    v = run(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "RU", "S5.1": SERVICES,
        "S5.5": "consulting", "S6.1": OUTSIDE_KZ, "S1.5": "KZT",
        "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 1_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.6": "no",
    }))

    assert v.kpn.convention_type == "full"
    assert v.kpn.rate == 0.0
    assert "F-TREATY-RATE" not in v.flags


# ── Потолок конвенции ─────────────────────────────────────────────────────

def test_code_rate_wins_when_it_is_lower_than_the_treaty_rate():
    """Абзац после пп. 9) п. 1 ст. 682: налогоплательщик ВПРАВЕ применить
    ставки международного договора. Значит договорная ставка — потолок, а не
    замена: если ставка кодекса ниже, применяется кодекс.

    Пакистан, вознаграждение по кредиту: кодекс даёт 10 % по пп. 7) п. 1
    ст. 682, конвенция — 12,5 %. Применяются 10 %."""
    v = run(base(**{
        "S1.1": {"quarter": 1, "year": 2026}, "S2.3": "PK", "S5.1": INTEREST,
        "S1.5": "KZT", "S4.1": date(2026, 3, 10), "S4.2": date(2026, 3, 20),
        "S4.4": 1_000_000.0, "S4.5": 1.0,
        "S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.5": "yes", "S7.6": "no",
    }))

    assert v.kpn.rate == 0.10                     # кодекс, не 0.125
    assert v.kpn.amount_kzt == 100_000
    assert "F-TREATY-CEILING" in v.flags


def test_no_ceiling_flag_when_the_treaty_is_actually_lower():
    """Обычный случай: конвенция ниже кодекса, потолок работает как льгота
    и отдельного предупреждения не требует."""
    v = run(dividends("RU", 10))

    assert v.kpn.rate == 0.10                     # конвенция ниже НК 15 %
    assert "F-TREATY-CEILING" not in v.flags


# ── Спорная ставка по дивидендам ──────────────────────────────────────────

def test_dividends_at_or_above_threshold_give_no_number_at_all():
    """Доля 25 % и выше — ставка спорна, движок вывод не даёт: ни ставки,
    ни суммы, ни графы I. Вместо них две позиции и что проверить."""
    v = run(dividends("RU", 70, **{"S7.2": "no", "S7.3": "no"}))

    assert v.kpn.applicable is None
    assert v.kpn.rate is None
    assert v.kpn.amount_kzt == 0
    assert v.graphs["I"] is None
    assert len(v.kpn.positions) == 2
    assert {p["id"] for p in v.kpn.positions} == {"pp6_5pct", "pp5_15pct"}
    assert v.kpn.what_to_check
    assert v.kpn.money_at_stake
    assert v.flag_severity("F-DIV-25") == "high"
    assert v.confidence == "manual_review"


def test_certificate_does_not_resolve_the_dispute():
    """Сертификат и конвенция спор не решают: под потолком 10 % остаются
    и 5 % по пп. 6), и 15 % по пп. 5)."""
    assert run(dividends("RU", 70)).kpn.rate is None
