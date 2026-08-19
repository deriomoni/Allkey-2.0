"""Схемы запросов и ответов помогайки 101.04.

Модуль stateless: ответы визарда приходят в теле POST, считаются и уходят
обратно. На сервере не остаётся ничего — ни черновика, ни истории прохождений.
Черновик живёт в браузере, как в модуле кадров.
"""
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    """Одна операция: полный набор ответов визарда.

    Ключи — идентификаторы вопросов из ТЗ §4 («S1.1», «S4.2», «S5.5»).
    Даты передаются строками в формате ISO, движок получает их уже разобранными.
    """
    answers: dict[str, Any] = Field(..., description="Ответы визарда: {questionId: value}")
    as_of_date: Optional[date] = Field(
        None, description="Дата расчёта; по умолчанию — дата выплаты из ответов")


class AggregateRequest(BaseModel):
    """Несколько операций за квартал — для строк основного расчёта."""
    operations: list[dict[str, Any]] = Field(..., min_length=1)
    as_of_date: Optional[date] = None


class FlagInfo(BaseModel):
    """Сработавшее предупреждение вместе с текстом из справочника.

    Отдаём текст сразу, чтобы фронтенд не тянул справочник и не собирал
    формулировки сам: тексты правил живут в данных, а не в интерфейсе.
    """
    code: str
    severity: str
    title: str
    text: str
    basis: Optional[str] = None
