"""Курсы валют Национального Банка РК.

Два тонких роута поверх готового клиента `nbrk_rates`. Отдельный домен, а не
часть помогайки: курсы — открытые данные, а не налоговая логика, и их будет
переиспользовать отдельный модуль курсов. Поэтому **гейта `f10104` здесь нет**,
достаточно обычной аутентификации.

Браузер не может обращаться к nationalbank.kz напрямую: сайт не отдаёт заголовки
CORS. Поэтому загрузка идёт через бэкенд, который заодно кэширует результат.

Контракт совпадает с прототипом `docs/prototypes/kursy-valyut.html`, поэтому
поля ответа в camelCase — их читает уже написанный интерфейс.

Клиент `nbrk_rates.py` живёт здесь же: домен самодостаточен и не зависит от
помогайки.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.rates.nbrk_rates import MAX_RANGE_DAYS, MemoryCache, NbrkRates, RangeRow
from app.users.models import User


class SkipTodayCache(MemoryCache):
    """Кэш, который не запоминает сегодняшний и будущие дни.

    Опубликованный курс за прошедшую дату не меняется никогда — его кэшируем
    навсегда, включая «в этот день публикации не было» для выходных. А вот
    сегодняшний день кэшировать нельзя: если спросить курс до публикации,
    в кэш ляжет «не публиковался», и до перезапуска процесса свежий курс
    уже не подтянется.

    Различие `...` («не спрашивали») и `None` («знаем, что публикации не было»)
    сохранено — на нём держится вся экономия запросов по выходным.
    """

    async def set(self, key: str, value) -> None:
        iso = key.split(":", 1)[-1]
        try:
            if date.fromisoformat(iso) >= date.today():
                return
        except ValueError:
            pass
        await super().set(key, value)


_client = NbrkRates(cache=SkipTodayCache())

router = APIRouter(prefix="/api/rates", tags=["rates"])


def _row(row: RangeRow) -> dict:
    return {
        "date": row.date,
        "code": row.code,
        "name": row.name,
        "rate": row.rate,
        "quant": row.quant,
        "carriedForward": row.carried_forward,
        "sourceDate": row.source_date,
    }


@router.get("")
async def rates_range(
    codes: str = Query("ALL", description="Коды валют через запятую либо ALL"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Курсы за период по списку валют.

    Пропуски заполняются переносом с последнего опубликованного дня, каждая
    такая строка помечена `carriedForward` — чтобы в интерфейсе было видно, что
    курс перенесён, а не подставлен молча.
    """
    wanted = [] if codes.strip().upper() == "ALL" else [
        c.strip().upper() for c in codes.split(",") if c.strip()
    ]

    if date_to < date_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Дата «по» раньше даты «с»")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Период больше {MAX_RANGE_DAYS} дней — разбейте на части")

    try:
        rows = await _client.get_range(wanted, date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Национальный Банк недоступен: {e}") from e

    return [_row(r) for r in rows]


@router.get("/official")
async def official_rate(
    code: str = Query(..., min_length=3, max_length=3),
    day: date = Query(..., alias="date"),
    _: User = Depends(get_current_user),
) -> dict:
    """Официальный курс на дату с переносом с предыдущего рабочего дня.

    Это то, что подставляется в поле курса на шаге «Даты и суммы». Если курс
    перенесён, `carriedForward` = true и `actualDate` показывает, с какой даты, —
    интерфейс обязан это показать, а не подставлять число молча.
    """
    try:
        official = await _client.get_official_rate(code.upper(), day)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Национальный Банк недоступен: {e}") from e

    if official is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Курс {code.upper()} на {day.isoformat()} не найден: "
                   "за последние 10 дней публикаций по этой валюте нет")

    return {
        "code": official.code,
        "name": official.name,
        "rate": official.rate,
        "quant": official.quant,
        "requestedDate": official.requested_date,
        "actualDate": official.actual_date,
        "carriedForward": official.carried_forward,
    }
