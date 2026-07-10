from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from decimal import Decimal


class LicensePlanBase(BaseModel):
    name: str
    description: str = ""
    price: Decimal = Decimal("0")
    duration_days: int
    is_active: bool = True
    is_default: bool = False
    badge_color: str = "#ef4444"


class LicensePlanCreate(LicensePlanBase):
    pass


class LicensePlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    duration_days: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    badge_color: Optional[str] = None


class LicensePlanResponse(LicensePlanBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserLicenseResponse(BaseModel):
    id: int
    user_id: int
    plan_id: int
    plan_name: str
    starts_at: datetime
    expires_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AssignLicenseRequest(BaseModel):
    user_id: int
    plan_id: int
