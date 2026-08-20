from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from app.database import get_db
from app.auth.dependencies import get_current_user, get_current_admin
from app.users.models import User
from app.services.models import Service, ServiceAccess, UserServiceOverride
from app.services.dependencies import user_available_services
from app.services.schemas import (
    ServiceMe, ServiceAdminResponse, ServiceOverrideInfo,
    ServiceCreate, ServiceUpdate, ServiceAccessUpdate, ServiceOverrideCreate,
)

router = APIRouter(prefix="/services", tags=["services"])


# ------- seed / migration (called once at startup from main.py) -------

SEED_SERVICES = [
    {"code": "case1", "title": "Сверка счёта 6010 с реестром ЭСФ",
     "description": "Карточка счёта 6010 ↔ реестр ЭСФ",
     "status": "production", "sort_order": 1, "roles": ["employee", "client"]},
    {"code": "case2", "title": "Сверка актов сверки взаиморасчётов",
     "description": "Акт сверки взаиморасчётов",
     "status": "production", "sort_order": 2, "roles": ["employee", "client"]},
    {"code": "case3", "title": "Сверка счёта 3310 с реестром ЭСФ",
     "description": "Карточка счёта 3310 ↔ реестр ЭСФ",
     "status": "production", "sort_order": 3, "roles": ["employee", "client"]},
    # Роли пусты намеренно: до выкатки помогайки кадровый модуль виден только
    # администратору. Основание — предупреждение автора модуля в
    # app/personnel/README.md: казахская колонка двуязычного трудового договора
    # собрана из словарей и ручных переводов и должна быть вычитана носителем
    # до использования с реальными клиентами. Вернуть доступ — дописать
    # "employee" обратно.
    # ВНИМАНИЕ: на уже развёрнутой базе эта правка ничего не изменит —
    # seed_services пропускает существующие сервисы. Там роль снимается на
    # экране «Доступы».
    {"code": "hr", "title": "Кадровые документы",
     "description": "Приём на работу: одна форма → пакет кадровых документов (ТД, приказ, согласия и др.).",
     "status": "beta", "sort_order": 6, "roles": []},
    # Роли пусты намеренно: первую версию помогайки проверяет только владелец,
    # сотрудникам она не выдаётся. Решение владельца от 20.08.2026 —
    # механизм тот же, которым выше закрыт кадровый модуль: администратор
    # видит статус beta и без выданной роли.
    # ВНИМАНИЕ: та же оговорка, что и для hr, — на развёрнутой базе правка
    # ничего не изменит, seed_services существующие сервисы не обновляет.
    # Открытие сотрудникам позже — выдача роли на экране «Доступы», не правка
    # кода: возвращать "employee" сюда не потребуется вовсе.
    {"code": "f10104", "title": "Помогайка по форме 101.04",
     "description": "Выплаты нерезидентам: КПН у источника и НДС за нерезидента, данные для формы 101.04.",
     "status": "beta", "sort_order": 7, "roles": []},
    {"code": "case_currency", "title": "Сверка курсов валют (USD 1С ↔ Нацбанк)",
     "description": "Карточка счёта в валюте ↔ курсы Нацбанка. Отклонение курса 1С от НБ.",
     "status": "beta", "sort_order": 4, "roles": ["employee"]},
    {"code": "case_bank", "title": "Сверка выписок (1С ↔ банк)",
     "description": "Карточка счёта 1С ↔ банковская выписка. Обороты, остатки, неучтённые поступления.",
     "status": "beta", "sort_order": 5, "roles": ["employee"]},
]


def seed_services(db: Session) -> None:
    """Идемпотентно наполнить реестр сервисов и мигрировать роли пользователей.

    - существующие пользователи роли 'user' становятся 'employee' (однократно);
    - сервисы из SEED_SERVICES создаются, если их ещё нет (существующие не трогаем).
    """
    # Миграция старой роли user -> employee.
    db.execute(text("UPDATE users SET role = 'employee' WHERE role = 'user'"))

    for spec in SEED_SERVICES:
        existing = db.query(Service).filter(Service.code == spec["code"]).first()
        if existing is not None:
            continue
        service = Service(
            code=spec["code"],
            title=spec["title"],
            description=spec["description"],
            status=spec["status"],
            is_enabled=True,
            sort_order=spec["sort_order"],
        )
        db.add(service)
        for role in spec["roles"]:
            db.add(ServiceAccess(service_code=spec["code"], role=role))

    db.commit()


# ------------------------------ helpers ------------------------------

def _admin_view(db: Session, service: Service) -> ServiceAdminResponse:
    roles = [
        a.role
        for a in db.query(ServiceAccess).filter(ServiceAccess.service_code == service.code).all()
    ]
    overrides = [
        ServiceOverrideInfo(user_id=o.user_id, allow=bool(o.allow))
        for o in db.query(UserServiceOverride)
        .filter(UserServiceOverride.service_code == service.code)
        .all()
    ]
    return ServiceAdminResponse(
        code=service.code,
        title=service.title,
        description=service.description or "",
        status=service.status,
        is_enabled=bool(service.is_enabled),
        sort_order=service.sort_order or 0,
        created_at=service.created_at,
        roles=roles,
        overrides=overrides,
    )


def _get_service_or_404(db: Session, code: str) -> Service:
    service = db.query(Service).filter(Service.code == code).first()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сервис не найден")
    return service


# ------------------------------ public (any authenticated) ------------------------------

@router.get("/me", response_model=List[ServiceMe])
async def my_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сервисы, доступные текущему пользователю."""
    services = user_available_services(db, current_user)
    return [
        ServiceMe(
            code=s.code,
            title=s.title,
            description=s.description or "",
            status=s.status,
        )
        for s in services
    ]


# ------------------------------ admin only ------------------------------

@router.get("", response_model=List[ServiceAdminResponse])
async def list_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    services = db.query(Service).order_by(Service.sort_order).all()
    return [_admin_view(db, s) for s in services]


@router.post("", response_model=ServiceAdminResponse)
async def create_service(
    data: ServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if db.query(Service).filter(Service.code == data.code).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сервис с таким кодом уже существует",
        )
    service = Service(
        code=data.code,
        title=data.title,
        description=data.description or "",
        status=data.status,
        is_enabled=data.is_enabled,
        sort_order=data.sort_order,
    )
    db.add(service)
    for role in set(data.roles):
        db.add(ServiceAccess(service_code=data.code, role=role))
    db.commit()
    db.refresh(service)
    return _admin_view(db, service)


@router.put("/{code}", response_model=ServiceAdminResponse)
async def update_service(
    code: str,
    data: ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    service = _get_service_or_404(db, code)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return _admin_view(db, service)


@router.put("/{code}/access", response_model=ServiceAdminResponse)
async def set_service_access(
    code: str,
    data: ServiceAccessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Переписать набор ролей, которым открыт сервис."""
    service = _get_service_or_404(db, code)
    db.query(ServiceAccess).filter(ServiceAccess.service_code == code).delete()
    for role in set(data.roles):
        db.add(ServiceAccess(service_code=code, role=role))
    db.commit()
    db.refresh(service)
    return _admin_view(db, service)


@router.post("/{code}/override", response_model=ServiceAdminResponse)
async def set_service_override(
    code: str,
    data: ServiceOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Создать/обновить персональное правило для пользователя."""
    service = _get_service_or_404(db, code)

    user = db.query(User).filter(User.id == data.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    override = (
        db.query(UserServiceOverride)
        .filter(
            UserServiceOverride.user_id == data.user_id,
            UserServiceOverride.service_code == code,
        )
        .first()
    )
    if override is None:
        override = UserServiceOverride(
            user_id=data.user_id, service_code=code, allow=data.allow
        )
        db.add(override)
    else:
        override.allow = data.allow
    db.commit()
    db.refresh(service)
    return _admin_view(db, service)


@router.delete("/{code}/override/{user_id}")
async def delete_service_override(
    code: str,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    deleted = (
        db.query(UserServiceOverride)
        .filter(
            UserServiceOverride.service_code == code,
            UserServiceOverride.user_id == user_id,
        )
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Персональное правило не найдено")
    return {"message": "Override deleted successfully"}
