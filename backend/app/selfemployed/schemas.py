"""Pydantic-схемы модуля «Договор с самозанятым».

Тело запроса один в один повторяет словарь, который принимает
`builder.build_context`, поэтому роутер отдаёт в билдер `data.model_dump()`
без промежуточных преобразований.

Осторожно с именами полей: `date` как имя поля pydantic затеняет импортированный
тип (см. app/personnel/README.md), поэтому дата договора — `contract_date`.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.selfemployed.profiles import ORDER


class CustomerIn(BaseModel):
    """Заказчик (при аренде — Арендатор). ИП подписывает по уведомлению о начале
    деятельности, поэтому должность/основание для него не используются."""
    org_form: Literal["ТОО", "АО", "ИП"] = "ТОО"
    name: str = Field(min_length=1)
    bin: str = Field(min_length=1, description="БИН, для ИП — ИИН")
    position: str = "Директор"
    position_gen: Optional[str] = Field(None, description="Должность в родительном падеже; пусто — склоним сами")
    head_name: str = Field(min_length=1)
    head_name_gen: Optional[str] = Field(None, description="ФИО руководителя в родительном падеже; пусто — склоним сами")
    basis_gen: str = "Устава"
    address: str = ""
    iik: str = ""
    bank: str = ""
    bik: str = ""
    phone: str = ""
    email: str = ""


class ExecutorIn(BaseModel):
    """Исполнитель (при аренде — Арендодатель) — самозанятое лицо.
    Пол определяется по 7-й цифре ИИН, отдельного поля нет."""
    full_name: str = Field(min_length=1)
    iin: str = Field(min_length=1)
    status: Literal["citizen", "kandas"] = "citizen"
    address: str = ""
    iik: str = ""
    bank: str = ""
    bik: str = ""
    phone: str = ""


class ContractRequest(BaseModel):
    """Данные формы. Суммы — целыми тенге (копейки в договорах не применяются)."""
    oked: str
    number: str = ""
    city: str = "г. Алматы"
    contract_date: date = Field(default_factory=date.today)
    valid_from: Optional[date] = Field(None, description="Пусто — договор действует с даты подписания")
    valid_to: date
    amount: int = Field(ge=1)
    payment_days: int = Field(20, ge=1, description="Срок оплаты, рабочих дней (п. 5.2)")
    payment_method: Literal["cashless", "any"] = "cashless"
    rent_period: Literal["month", "term"] = "month"
    notice_days: Optional[int] = Field(None, ge=1, description="Пусто — срок уведомления из профиля ОКЭД")
    subject: Optional[str] = Field(None, description="Пусто — предмет по умолчанию для выбранного ОКЭД")
    customer: CustomerIn
    executor: ExecutorIn

    @field_validator("oked")
    @classmethod
    def _known_oked(cls, value: str) -> str:
        if value not in ORDER:
            raise ValueError(f"Неизвестный вид деятельности (ОКЭД): {value}")
        return value


class OkedInfo(BaseModel):
    """Строка справочника для селекта на форме."""
    code: str
    name: str
    kind: Literal["works", "services", "rent"]
    title: str
    default_subject: str
    notice_days: int


class CheckResponse(BaseModel):
    """Предупреждения формы — показываются, но не блокируют генерацию."""
    warnings: List[str]
