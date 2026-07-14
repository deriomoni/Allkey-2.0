from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.users.models import User
from app.services.models import Service, ServiceAccess, UserServiceOverride


def user_has_service(db: Session, user: User, code: str) -> bool:
    """Может ли пользователь видеть/использовать сервис `code`.

    Порядок проверки строго такой:
    1. admin → всегда True (владелец видит всё, включая beta и отключённые).
    2. Сервиса нет или is_enabled == False → False.
    3. Персональный override для (user, code) → вернуть его allow (перебивает роль).
    4. Есть service_access для (code, user.role) → True.
    5. Иначе → False.
    """
    if user.role == "admin":
        return True

    service = db.query(Service).filter(Service.code == code).first()
    if service is None or not service.is_enabled:
        return False

    override = (
        db.query(UserServiceOverride)
        .filter(
            UserServiceOverride.user_id == user.id,
            UserServiceOverride.service_code == code,
        )
        .first()
    )
    if override is not None:
        return bool(override.allow)

    access = (
        db.query(ServiceAccess)
        .filter(
            ServiceAccess.service_code == code,
            ServiceAccess.role == user.role,
        )
        .first()
    )
    return access is not None


def user_available_services(db: Session, user: User) -> List[Service]:
    """Список доступных пользователю сервисов, отсортированный по sort_order."""
    services = db.query(Service).order_by(Service.sort_order).all()

    if user.role == "admin":
        # Владелец видит всё, включая beta и отключённые.
        return services

    return [s for s in services if user_has_service(db, user, s.code)]


def require_service(code: str):
    """Фабрика зависимостей: доступ к эндпоинту только тем, кому открыт сервис `code`."""

    async def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not user_has_service(db, current_user, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Этот сервис вам недоступен",
            )
        return current_user

    return _dep
