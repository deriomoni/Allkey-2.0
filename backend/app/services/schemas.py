from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class ServiceMe(BaseModel):
    """Сервис в виде, доступном обычному пользователю (GET /services/me)."""
    code: str
    title: str
    description: str = ""
    status: str


class ServiceOverrideInfo(BaseModel):
    user_id: int
    allow: bool


class ServiceAdminResponse(BaseModel):
    """Полная карточка сервиса + матрица доступа (для админа)."""
    code: str
    title: str
    description: str = ""
    status: str
    is_enabled: bool
    sort_order: int
    created_at: Optional[datetime] = None
    roles: List[str] = []                       # роли с доступом
    overrides: List[ServiceOverrideInfo] = []   # персональные исключения


class ServiceCreate(BaseModel):
    code: str
    title: str
    description: str = ""
    status: str = "production"
    is_enabled: bool = True
    sort_order: int = 0
    roles: List[str] = []


class ServiceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class ServiceAccessUpdate(BaseModel):
    roles: List[str]


class ServiceOverrideCreate(BaseModel):
    user_id: int
    allow: bool = True
