"""Роуты курсов НБ РК. Сеть не нужна: `get_day` подменяется.

Проверяется то, за что отвечает именно роутер: доступ, контракт ответа,
ограничение периода, ALL, перенос курса с выходных и осторожность кэша
с сегодняшним днём. Разбор XML и нормализация по `quant` покрыты тестами
самого клиента.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.rates.nbrk_rates import Rate
from app.rates import router as rates_module


PUBLISHED = {
    "2026-06-11": [Rate(code="USD", name="ДОЛЛАР США", rate=464.02, quant=1, raw=464.02),
                   Rate(code="EUR", name="ЕВРО", rate=536.18, quant=1, raw=536.18)],
    "2026-06-12": [Rate(code="USD", name="ДОЛЛАР США", rate=465.00, quant=1, raw=465.00),
                   Rate(code="EUR", name="ЕВРО", rate=537.00, quant=1, raw=537.00)],
}


@pytest.fixture
def client(monkeypatch):
    async def fake_get_day(self, day):
        iso = day if isinstance(day, str) else day.isoformat()
        return PUBLISHED.get(iso)

    monkeypatch.setattr(rates_module.NbrkRates, "get_day", fake_get_day)

    app = FastAPI()
    app.include_router(rates_module.router)

    def _client(authenticated=True):
        if authenticated:
            user = SimpleNamespace(id=1, email="t@t.kz", full_name="Тест",
                                   role="client", is_active=True)
            app.dependency_overrides[get_current_user] = lambda: user
        else:
            app.dependency_overrides.pop(get_current_user, None)
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()


# ── Доступ ────────────────────────────────────────────────────────────────

def test_range_requires_authentication(client):
    response = client(False).get("/api/rates", params={"codes": "USD", "from": "2026-06-11",
                                                       "to": "2026-06-12"})
    assert response.status_code == 401


def test_official_requires_authentication(client):
    response = client(False).get("/api/rates/official", params={"code": "USD",
                                                                "date": "2026-06-11"})
    assert response.status_code == 401


def test_plain_client_role_is_enough(client):
    """Гейта f10104 здесь нет: курсы — открытые данные, а не налоговая логика.
    Роль `client` без доступа к помогайке курсы получить может."""
    response = client().get("/api/rates", params={"codes": "USD", "from": "2026-06-11",
                                                  "to": "2026-06-12"})
    assert response.status_code == 200


# ── Контракт ответа ───────────────────────────────────────────────────────

def test_range_returns_prototype_contract(client):
    body = client().get("/api/rates", params={"codes": "USD", "from": "2026-06-11",
                                              "to": "2026-06-11"}).json()

    assert body == [{
        "date": "2026-06-11", "code": "USD", "name": "ДОЛЛАР США",
        "rate": 464.02, "quant": 1, "carriedForward": False,
        "sourceDate": "2026-06-11",
    }]


def test_range_marks_carried_forward_days(client):
    """13 и 14 июня публикаций нет — курс переносится с 12-го и помечается.

    На живом фиде эта ветка не воспроизводится: НБ РК публикует курс каждый
календарный день, включая выходные и главные праздники (проверено: суббота
13.06.2026 и воскресенье 14.06.2026 — 489,33; 01.01.2026 — 505,53; Наурыз
22.03.2026 — 482,33). Правило «курс применяется со следующего рабочего дня
после торгов» Нацбанк применяет у себя, и в фид попадает уже результат.

Тест держим на моке. Механизм в коде — чисто техническая страховка на сбой
фида и очень старые даты: нормы, обязывающей применять последний определённый
курс, в новом кодексе нет. Правила курса исчерпываются ст. 21 пп. 3).
    """
    body = client().get("/api/rates", params={"codes": "USD", "from": "2026-06-11",
                                              "to": "2026-06-14"}).json()

    assert [r["date"] for r in body] == ["2026-06-11", "2026-06-12", "2026-06-13", "2026-06-14"]
    assert [r["carriedForward"] for r in body] == [False, False, True, True]
    assert body[3]["sourceDate"] == "2026-06-12"
    assert body[3]["rate"] == 465.00


def test_codes_all_returns_every_currency(client):
    body = client().get("/api/rates", params={"codes": "ALL", "from": "2026-06-11",
                                              "to": "2026-06-11"}).json()

    assert {r["code"] for r in body} == {"USD", "EUR"}


def test_official_returns_carry_forward_details(client):
    body = client().get("/api/rates/official", params={"code": "USD",
                                                       "date": "2026-06-14"}).json()

    assert body["rate"] == 465.00
    assert body["requestedDate"] == "2026-06-14"
    assert body["actualDate"] == "2026-06-12"
    assert body["carriedForward"] is True


def test_official_unknown_currency_is_404_not_invented(client):
    response = client().get("/api/rates/official", params={"code": "XYZ",
                                                           "date": "2026-06-11"})
    assert response.status_code == 404


# ── Границы ───────────────────────────────────────────────────────────────

def test_range_over_400_days_rejected(client):
    response = client().get("/api/rates", params={"codes": "USD", "from": "2026-01-01",
                                                  "to": "2027-06-01"})
    assert response.status_code == 400
    assert "400" in response.json()["detail"]


def test_reversed_range_rejected(client):
    response = client().get("/api/rates", params={"codes": "USD", "from": "2026-06-12",
                                                  "to": "2026-06-11"})
    assert response.status_code == 400


# ── Кэш ───────────────────────────────────────────────────────────────────

def test_cache_keeps_past_days_including_empty_ones():
    """Прошедший выходной кэшируется как «публикации не было»: различие
    `...` и `None` сохранено, иначе каждый запрос выходного дня снова
    дёргал бы Нацбанк."""
    cache = rates_module.SkipTodayCache()
    import asyncio

    asyncio.run(cache.set("nbrk:2026-06-13", None))
    assert asyncio.run(cache.get("nbrk:2026-06-13")) is None      # знаем: пусто
    assert asyncio.run(cache.get("nbrk:2026-06-14")) is ...        # не спрашивали


def test_cache_refuses_to_memoize_today():
    """Сегодняшний день не кэшируется: спросив курс до публикации, иначе
    запомнили бы «не публиковался» до перезапуска процесса."""
    cache = rates_module.SkipTodayCache()
    import asyncio

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    asyncio.run(cache.set(f"nbrk:{today}", None))
    asyncio.run(cache.set(f"nbrk:{tomorrow}", None))

    assert asyncio.run(cache.get(f"nbrk:{today}")) is ...
    assert asyncio.run(cache.get(f"nbrk:{tomorrow}")) is ...
