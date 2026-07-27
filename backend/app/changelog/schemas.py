from pydantic import BaseModel
from datetime import date as _date, datetime
from typing import Optional


class ChangelogResponse(BaseModel):
    id: int
    date: _date
    category: str
    service_code: Optional[str] = None
    title: str
    body: str = ""
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChangelogCreate(BaseModel):
    date: _date
    category: str                       # "fix" | "feature" | "improvement"
    service_code: Optional[str] = None
    title: str
    body: str = ""


class ChangelogUpdate(BaseModel):
    date: Optional[_date] = None
    category: Optional[str] = None
    service_code: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
