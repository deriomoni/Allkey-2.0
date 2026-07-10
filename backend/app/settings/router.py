from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict
from app.database import get_db
from app.auth.dependencies import get_current_admin
from app.users.models import User
from app.settings.models import AppSettings
from app.settings.schemas import SettingsPublicResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])

PUBLIC_KEYS = ["whatsapp_number", "telegram_link", "kaspi_payment_url"]


def get_settings_dict(db: Session, keys: list[str] | None = None) -> Dict[str, str]:
    query = db.query(AppSettings)
    if keys:
        query = query.filter(AppSettings.key.in_(keys))
    settings = query.all()
    return {s.key: s.value for s in settings}


@router.get("/public", response_model=SettingsPublicResponse)
async def get_public_settings(db: Session = Depends(get_db)):
    """Get public settings for purchase modal."""
    data = get_settings_dict(db, PUBLIC_KEYS)
    return SettingsPublicResponse(
        whatsapp_number=data.get("whatsapp_number", ""),
        telegram_link=data.get("telegram_link", ""),
        kaspi_payment_url=data.get("kaspi_payment_url", ""),
    )


@router.get("", response_model=Dict[str, str])
async def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all settings (admin only)."""
    return get_settings_dict(db)


@router.put("")
async def update_settings(
    data: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update settings (admin only)."""
    for key, value in data.settings.items():
        setting = db.query(AppSettings).filter(AppSettings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSettings(key=key, value=value)
            db.add(setting)

    db.commit()
    return {"message": "Settings updated successfully"}
