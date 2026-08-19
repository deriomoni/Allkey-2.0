"""
Курсы валют Национального Банка РК — загрузка, нормализация, кэш.

Порт nbrk-rates.js под бэкенд Allkey (FastAPI + SQLAlchemy).
Разбор XML — на stdlib, сетевой слой — httpx (уже есть в стеке FastAPI через TestClient).
Если httpx недоступен, замените _fetch() на requests/urllib: логика разбора от него не зависит.

Источник (проверено 17.08.2026, ключей и лимитов нет):
    за дату      GET https://nationalbank.kz/rss/get_rates.cfm?fdate=ДД.ММ.ГГГГ
    последние    GET https://nationalbank.kz/rss/rates_all.xml

ТРИ ВЕЩИ, КОТОРЫЕ ЛОМАЮТ НАЛОГОВЫЙ РАСЧЁТ, ЕСЛИ ИХ НЕ УЧЕСТЬ
─────────────────────────────────────────────────────────────
1. Курс указан за `quant` единиц. Нормализованный = description / quant.
   У иены quant = 100: сырое 292.00 означает 2.92 ₸ за иену.
2. В выходные и праздники НБ РК не публикует. Действующим считается последний
   опубликованный. get_official_rate() ищет назад и помечает результат
   carried_forward, чтобы перенос был виден в интерфейсе, а не подставлялся молча.
3. Опубликованный курс за прошедшую дату не меняется. Кэш — навсегда, без TTL.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Iterable, Protocol, Sequence

import httpx

BASE = "https://nationalbank.kz"
UA = "allkey.kz rates loader"
MAX_RANGE_DAYS = 400
MAX_CARRY_BACK_DAYS = 10


# ─────────────────────────── модели ───────────────────────────

@dataclass(frozen=True, slots=True)
class Rate:
    code: str
    name: str | None
    rate: float          # нормализованный, за 1 единицу
    quant: int
    raw: float           # как в фиде, за quant единиц
    change: float = 0.0
    pub_date: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialRate:
    code: str
    name: str | None
    rate: float
    quant: int
    requested_date: str
    actual_date: str
    carried_forward: bool

    def dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RangeRow:
    date: str
    code: str
    name: str | None
    rate: float
    quant: int
    carried_forward: bool
    source_date: str

    def dict(self) -> dict:
        return asdict(self)


class Cache(Protocol):
    """Минимальный контракт. Подставьте БД или Redis по соглашениям проекта."""
    async def get(self, key: str): ...
    async def set(self, key: str, value) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._d: dict = {}

    async def get(self, key: str):
        return self._d.get(key, ...)          # ... = «не знаем», None = «знаем, что пусто»

    async def set(self, key: str, value) -> None:
        self._d[key] = value

    def __len__(self) -> int:
        return len(self._d)


# ─────────────────────────── даты ───────────────────────────

def to_nbrk_date(d: date | str) -> str:
    d = _as_date(d)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _as_date(d: date | str) -> date:
    return d if isinstance(d, date) else date.fromisoformat(d)


def each_day(start: date | str, end: date | str) -> list[str]:
    a, b = _as_date(start), _as_date(end)
    if b < a:
        raise ValueError("Дата «по» раньше даты «с»")
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


# ─────────────────────────── разбор XML ───────────────────────────
# Фид плоский и стабильный; полноценный парсер не нужен, а regex не тянет зависимость
# и не падает на некорректно закрытых тегах, которые у НБ РК периодически встречаются.

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&"))


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S | re.I)
    if not m:
        return None
    v = m.group(1)
    for a, b in _ENTITIES:
        v = v.replace(a, b)
    return v.strip()


def _num(s: str | None, default: float = 0.0) -> float:
    if s is None:
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def parse_rates_xml(xml: str) -> tuple[str | None, list[Rate]]:
    """Разбирает оба формата фида. Возвращает (дата документа, список курсов)."""
    doc_date = _tag(xml, "date")          # есть в get_rates.cfm
    rates: list[Rate] = []

    for block in _ITEM_RE.findall(xml):
        code = _tag(block, "title")
        raw_s = _tag(block, "description")
        if not code or raw_s is None:
            continue
        quant = int(_num(_tag(block, "quant"), 1)) or 1
        raw = _num(raw_s, float("nan"))
        if raw != raw:                     # NaN
            continue
        rates.append(Rate(
            code=code.upper(),
            name=_tag(block, "fullname"),
            rate=raw / quant,
            quant=quant,
            raw=raw,
            change=_num(_tag(block, "change")),
            pub_date=_tag(block, "pubDate"),
        ))

    if not doc_date and rates:
        doc_date = rates[0].pub_date
    return doc_date, rates


# ─────────────────────────── клиент ───────────────────────────

class NbrkRates:
    def __init__(
        self,
        cache: Cache | None = None,
        *,
        base: str = BASE,
        concurrency: int = 4,
        timeout: float = 15.0,
        retries: int = 3,
    ) -> None:
        self.cache = cache or MemoryCache()
        self.base = base.rstrip("/")
        self.concurrency = concurrency
        self.timeout = timeout
        self.retries = retries

    async def _fetch(self, url: str) -> str:
        last: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as cli:
            for attempt in range(self.retries + 1):
                try:
                    r = await cli.get(url, headers={"User-Agent": UA,
                                                    "Accept": "application/xml,text/xml,*/*"})
                    r.raise_for_status()
                    return r.text
                except Exception as e:                     # noqa: BLE001
                    last = e
                    if attempt < self.retries:
                        await asyncio.sleep(0.4 * 2 ** attempt)
        raise RuntimeError(f"Не удалось получить {url}: {last}")

    async def get_day(self, day: date | str) -> list[Rate] | None:
        """Курсы всех валют на дату. None — публикации не было (выходной, праздник)."""
        iso = _as_date(day).isoformat()
        key = f"nbrk:{iso}"

        cached = await self.cache.get(key)
        if cached is not ...:
            return cached

        xml = await self._fetch(f"{self.base}/rss/get_rates.cfm?fdate={to_nbrk_date(iso)}")
        _, rates = parse_rates_xml(xml)
        value = rates or None
        await self.cache.set(key, value)
        return value

    async def get_latest(self) -> tuple[str | None, list[Rate]]:
        """Последние опубликованные курсы. Кэшировать не дольше часа."""
        return parse_rates_xml(await self._fetch(f"{self.base}/rss/rates_all.xml"))

    async def get_official_rate(
        self, code: str, day: date | str, max_back: int = MAX_CARRY_BACK_DAYS
    ) -> OfficialRate | None:
        """
        Официальный курс на дату с переносом с предыдущего рабочего дня.
        Это то, что вызывает помогайка 101.04.
        """
        code = code.upper()
        target = _as_date(day)
        for back in range(max_back + 1):
            d = (target - timedelta(days=back)).isoformat()
            rates = await self.get_day(d)
            if not rates:
                continue
            hit = next((r for r in rates if r.code == code), None)
            if hit is None:
                continue
            return OfficialRate(
                code=code, name=hit.name, rate=hit.rate, quant=hit.quant,
                requested_date=target.isoformat(), actual_date=d,
                carried_forward=back > 0,
            )
        return None

    async def get_range(
        self,
        codes: Sequence[str],
        start: date | str,
        end: date | str,
        *,
        fill_gaps: bool = True,
        on_progress=None,
    ) -> list[RangeRow]:
        """
        Диапазон дат по списку валют. Пустой codes — все валюты.
        Это то, что вызывает экран «Курсы валют» и предзагрузка в помогайке.
        """
        want = [c.upper() for c in codes]
        days = each_day(start, end)
        if len(days) > MAX_RANGE_DAYS:
            raise ValueError(f"Диапазон больше {MAX_RANGE_DAYS} дней — разбейте на части")

        sem = asyncio.Semaphore(self.concurrency)
        by_date: dict[str, list[Rate] | None] = {}
        done = 0

        async def one(d: str) -> None:
            nonlocal done
            async with sem:
                try:
                    by_date[d] = await self.get_day(d)
                except Exception:                          # noqa: BLE001
                    by_date[d] = None                      # день пропускаем, не валим весь диапазон
                done += 1
                if on_progress:
                    on_progress(done, len(days))

        await asyncio.gather(*(one(d) for d in days))

        out: list[RangeRow] = []
        last: dict[str, tuple[Rate, str]] = {}

        for d in days:
            for r in (by_date.get(d) or []):
                last[r.code] = (r, d)

            for code in (want or list(last.keys())):
                known = last.get(code)
                if known is None:
                    continue                               # валюта ещё не встречалась
                rate, src = known
                carried = src != d
                if carried and not fill_gaps:
                    continue
                out.append(RangeRow(
                    date=d, code=code, name=rate.name, rate=rate.rate,
                    quant=rate.quant, carried_forward=carried, source_date=src,
                ))
        return out


# ─────────────────────────── выгрузка ───────────────────────────

def to_csv(rows: Iterable[RangeRow]) -> str:
    """CSV под русский Excel: точка с запятой, десятичная запятая, BOM добавляется при отдаче."""
    head = "Дата;Код;Валюта;Курс за 1 ед.;Перенос;Дата источника"
    lines = [head]
    for r in rows:
        lines.append(";".join([
            r.date, r.code, (r.name or ""),
            f"{r.rate}".replace(".", ","),
            "да" if r.carried_forward else "",
            r.source_date,
        ]))
    return "\n".join(lines)
