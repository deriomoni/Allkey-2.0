"""Тесты загрузчика курсов НБ РК. Сеть не требуется — get_day подменяется.

Порт присланного `test_nbrk_rates.py` под pytest: исходник был самостоятельным
скриптом (печать «OK/FAIL» и `raise SystemExit` на верхнем уровне модуля).
Под pytest такой файл падает ещё на сборке, поэтому проверки переписаны как
тест-функции — все 22 сохранены один в один, ни одна не ослаблена и не добавлена.

pytest-asyncio в проекте нет и заводить его ради четырёх корутин незачем:
асинхронные проверки запускаются через `asyncio.run` внутри обычных тестов.
"""
import asyncio

from app.rates.nbrk_rates import (
    NbrkRates, Rate, each_day, parse_rates_xml, to_csv, to_nbrk_date,
)

FX_DAY = """<?xml version="1.0" encoding="utf-8"?>
<rates><title>Official exchange rates</title><date>17.08.2026</date>
<item><fullname>ДОЛЛАР США</fullname><title>USD</title><description>464.02</description><quant>1</quant><change>0.00</change></item>
<item><fullname>ЕВРО</fullname><title>EUR</title><description>536.18</description><quant>1</quant><change>0.00</change></item>
<item><fullname>ЯПОНСКАЯ ИЕНА</fullname><title>JPY</title><description>292.00</description><quant>100</quant><change>0.00</change></item>
</rates>"""

FX_RSS = """<rss version="2.0"><channel>
<item><title>USD</title><pubDate>18.08.2026</pubDate><description>461.39</description><quant>1</quant><index>DOWN</index><change>-2.63</change></item>
</channel></rss>"""


class Fake(NbrkRates):
    """Клиент без сети: published — {дата в ISO: [Rate]}."""

    def __init__(self, published):
        super().__init__()
        self.published = published

    async def get_day(self, day):
        iso = day if isinstance(day, str) else day.isoformat()
        return self.published.get(iso)


def U(v: float) -> Rate:
    return Rate(code="USD", name="ДОЛЛАР США", rate=v, quant=1, raw=v)


# ── разбор XML ────────────────────────────────────────────────────────────

def test_doc_date_parsed():
    assert parse_rates_xml(FX_DAY)[0] == "17.08.2026"


def test_all_currencies_parsed():
    assert len(parse_rates_xml(FX_DAY)[1]) == 3


def test_usd_rate():
    rates = parse_rates_xml(FX_DAY)[1]
    assert rates[0].code == "USD" and rates[0].rate == 464.02


def test_jpy_normalised_by_quant():
    """Иена: сырое 292.00 при quant=100 → 2.92 ₸ за иену."""
    jpy = next(r for r in parse_rates_xml(FX_DAY)[1] if r.code == "JPY")
    assert abs(jpy.rate - 2.92) < 1e-9
    assert jpy.raw == 292.00


def test_pubdate_used_when_no_doc_date():
    assert parse_rates_xml(FX_RSS)[0] == "18.08.2026"


def test_change_keeps_sign():
    assert parse_rates_xml(FX_RSS)[1][0].change == -2.63


def test_weekend_feed_is_empty_not_error():
    assert parse_rates_xml("<rates><date>16.08.2026</date></rates>")[1] == []


# ── даты ──────────────────────────────────────────────────────────────────

def test_nbrk_date_format():
    assert to_nbrk_date("2026-01-05") == "05.01.2026"


def test_each_day_inclusive():
    assert len(each_day("2026-01-01", "2026-01-05")) == 5


def test_reversed_range_raises():
    try:
        each_day("2026-02-01", "2026-01-01")
    except ValueError:
        return
    raise AssertionError("обратный диапазон должен давать ValueError")


# ── перенос курса ─────────────────────────────────────────────────────────
# ИСКУССТВЕННЫЙ СЛУЧАЙ. На живом фиде эта ветка не воспроизводится: НБ РК публикует курс каждый
# календарный день, включая выходные и главные праздники (проверено: суббота
# 13.06.2026 и воскресенье 14.06.2026 — 489,33; 01.01.2026 — 505,53; Наурыз
# 22.03.2026 — 482,33). Правило «курс применяется со следующего рабочего дня
# после торгов» Нацбанк применяет у себя, и в фид попадает уже результат.

# Тест держим на моке, а сам механизм — в коде: он требуется по существу нормы.
# Пункт 5 статьи 190 обязывает применять последний определённый курс, если на
# дату операции курс не определялся. Норма есть — обработка должна быть.
# Плюс страховка на сбой фида и на очень старые даты.

def test_sunday_carries_friday_rate():
    api = Fake({"2026-08-14": [U(464.02)]})
    r = asyncio.run(api.get_official_rate("USD", "2026-08-16"))  # воскресенье
    assert r is not None
    assert r.carried_forward is True
    assert r.actual_date == "2026-08-14"


def test_unknown_currency_is_none_not_invented():
    api = Fake({"2026-08-14": [U(464.02)]})
    assert asyncio.run(api.get_official_rate("XYZ", "2026-08-16")) is None


def test_publication_on_the_day_is_not_carried():
    api = Fake({"2026-08-14": [U(464.02)]})
    r = asyncio.run(api.get_official_rate("USD", "2026-08-14"))
    assert r is not None and r.carried_forward is False


def test_no_search_beyond_ten_days_back():
    api = Fake({"2026-07-01": [U(1)]})
    assert asyncio.run(api.get_official_rate("USD", "2026-08-16")) is None


# ── диапазон ──────────────────────────────────────────────────────────────

def _range_api() -> Fake:
    return Fake({"2026-08-13": [U(463.0)], "2026-08-14": [U(464.02)]})


def test_range_fills_every_day():
    rows = asyncio.run(_range_api().get_range(["USD"], "2026-08-13", "2026-08-16"))
    assert len(rows) == 4


def test_range_marks_carried_row():
    rows = asyncio.run(_range_api().get_range(["USD"], "2026-08-13", "2026-08-16"))
    assert rows[2].carried_forward is True
    assert rows[2].rate == 464.02
    assert rows[2].source_date == "2026-08-14"


def test_range_keeps_own_publication():
    rows = asyncio.run(_range_api().get_range(["USD"], "2026-08-13", "2026-08-16"))
    assert rows[0].rate == 463.0 and rows[0].carried_forward is False


def test_range_without_fill_gaps_skips_weekend():
    rows = asyncio.run(
        _range_api().get_range(["USD"], "2026-08-13", "2026-08-16", fill_gaps=False)
    )
    assert len(rows) == 2


def test_range_over_limit_raises():
    try:
        asyncio.run(_range_api().get_range(["USD"], "2026-01-01", "2027-06-01"))
    except ValueError:
        return
    raise AssertionError("диапазон свыше 400 дней должен давать ValueError")


def test_progress_reaches_the_end():
    prog: list[tuple[int, int]] = []
    asyncio.run(_range_api().get_range(
        ["USD"], "2026-08-13", "2026-08-16", on_progress=lambda a, b: prog.append((a, b))
    ))
    assert prog and prog[-1] == (4, 4)


# ── выгрузка ──────────────────────────────────────────────────────────────

def test_csv_has_header_plus_rows():
    rows = asyncio.run(_range_api().get_range(["USD"], "2026-08-13", "2026-08-16"))
    assert len(to_csv(rows).split("\n")) == 5


def test_csv_uses_decimal_comma():
    rows = asyncio.run(_range_api().get_range(["USD"], "2026-08-13", "2026-08-16"))
    assert "464,02" in to_csv(rows)
