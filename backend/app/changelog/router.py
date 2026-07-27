from datetime import date as _date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.auth.dependencies import get_current_admin, require_staff
from app.users.models import User
from app.changelog.models import ChangelogEntry
from app.changelog.schemas import (
    ChangelogResponse, ChangelogCreate, ChangelogUpdate,
)

router = APIRouter(prefix="/changelog", tags=["changelog"])

CATEGORIES = ("fix", "feature", "improvement")


# ------- seed (called once at startup from main.py) -------

def seed_changelog(db: Session) -> None:
    """Идемпотентно создать первую запись журнала, если он пуст."""
    if db.query(ChangelogEntry).first() is not None:
        return
    db.add(ChangelogEntry(
        date=_date(2026, 7, 27),
        category="fix",
        service_code="case_bank",
        title="Исправлен разбор валютной карточки счёта 1С",
        body=(
            "Сверка выписки не видела операции 1С при валютной карточке счёта: суммовая "
            "колонка определялась по заголовкам, и колонка с кодом валюты (EUR), стоящая "
            "в данных без заголовка, перехватывала колонку суммы. Теперь суммовая колонка "
            "определяется по фактическим данным читаемых строк. Проверено на выписке "
            "Народного банка: распознано 39 операций 1С, сопоставлено 37. Оба формата "
            "выгрузки карточки (только валюта / валюта + тенговый эквивалент) дают "
            "одинаковый результат."
        ),
    ))
    db.commit()


# ------------------------------ helpers ------------------------------

def _validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимая категория (fix | feature | improvement)",
        )


def _get_entry_or_404(db: Session, entry_id: int) -> ChangelogEntry:
    entry = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return entry


# ------------------------------ staff (admin + employee) ------------------------------

@router.get("", response_model=List[ChangelogResponse])
async def list_changelog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Журнал изменений. Виден сотрудникам и владельцу, клиентам — 403."""
    return (
        db.query(ChangelogEntry)
        .order_by(ChangelogEntry.date.desc(), ChangelogEntry.id.desc())
        .all()
    )


# ------------------------------ admin only ------------------------------

@router.post("", response_model=ChangelogResponse)
async def create_changelog(
    data: ChangelogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _validate_category(data.category)
    entry = ChangelogEntry(
        date=data.date,
        category=data.category,
        service_code=(data.service_code or None),
        title=data.title,
        body=data.body or "",
        created_by=current_user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=ChangelogResponse)
async def update_changelog(
    entry_id: int,
    data: ChangelogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    entry = _get_entry_or_404(db, entry_id)
    update_data = data.model_dump(exclude_unset=True)
    if "category" in update_data:
        _validate_category(update_data["category"])
    if "service_code" in update_data:
        update_data["service_code"] = update_data["service_code"] or None
    for field, value in update_data.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
async def delete_changelog(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    entry = _get_entry_or_404(db, entry_id)
    db.delete(entry)
    db.commit()
    return {"message": "Changelog entry deleted successfully"}
