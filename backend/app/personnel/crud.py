"""CRUD for the employer directory (Company).

The module is stateless for employees' personal data — only Company is stored
(legal-entity requisites from the open registry, ТЗ §5). Employee/Employment are
never persisted; they live in the client draft and are rendered from the request
body (see router.py).

PII rule (ТЗ §9): БИН travels only in request/response bodies; lookups use the
internal id; nothing is written to the application log.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.personnel import schemas as s
from app.personnel.helpers.iin import is_valid_bin
from app.personnel.models import Company, PositionTranslation
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "hr"

crud_router = APIRouter(prefix="/personnel", tags=["personnel-crud"])


def _require_valid_bin(bin_value: str) -> None:
    if bin_value and not is_valid_bin(bin_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный БИН")


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Компания не найдена")
    return company


@crud_router.post("/companies", response_model=s.CompanyResponse)
async def create_company(data: s.CompanyCreate, db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    _require_valid_bin(data.bin)
    company = Company(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@crud_router.get("/companies", response_model=List[s.CompanyResponse])
async def list_companies(db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    return db.query(Company).order_by(Company.name_ru).all()


@crud_router.get("/companies/{company_id}", response_model=s.CompanyResponse)
async def get_company(company_id: int, db: Session = Depends(get_db),
                      _u: User = Depends(require_service(SERVICE_CODE))):
    return _get_company_or_404(db, company_id)


@crud_router.put("/companies/{company_id}", response_model=s.CompanyResponse)
async def update_company(company_id: int, data: s.CompanyUpdate, db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    company = _get_company_or_404(db, company_id)
    if data.bin is not None:
        _require_valid_bin(data.bin)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company


# --- Справочник должностей рус→каз (§4.2) ---------------------------------
# Единственное ручное казахское поле в форме приёма. При первом вводе должности
# пара сохраняется; в следующий раз казахский вариант подставляется автоматически.
# Должность — не персональные данные, поэтому запрос по значению допустим.

def _norm_ru(position_ru: str) -> str:
    """Ключ справочника: без лишних пробелов и в нижнем регистре. Нормализуем в Python,
    а сравниваем точным равенством — не зависим от того, как БД сворачивает регистр
    кириллицы (SQLite lower() кириллицу не трогает, Postgres — трогает). Значение
    position_ru в справочнике служит только ключом и пользователю не показывается."""
    return " ".join(position_ru.split()).strip().lower()


@crud_router.get("/positions/translate", response_model=s.PositionTranslationOut)
async def translate_position(ru: str, db: Session = Depends(get_db),
                             _u: User = Depends(require_service(SERVICE_CODE))):
    """Подобрать казахский вариант должности по русскому (без учёта регистра/пробелов).
    Если пары нет — возвращаем пустой казахский, чтобы клиент показал поле для ввода."""
    key = _norm_ru(ru)
    row = db.query(PositionTranslation).filter(PositionTranslation.position_ru == key).first()
    if row:
        return row
    return s.PositionTranslationOut(position_ru=key, position_kk="")


@crud_router.post("/positions/translate", response_model=s.PositionTranslationOut)
async def save_position_translation(data: s.PositionTranslationIn, db: Session = Depends(get_db),
                                    _u: User = Depends(require_service(SERVICE_CODE))):
    """Сохранить/обновить пару «должность рус → каз». Пустой казахский не сохраняем."""
    key = _norm_ru(data.position_ru)
    kk = data.position_kk.strip()
    if not key or not kk:
        return s.PositionTranslationOut(position_ru=key, position_kk=kk)
    row = db.query(PositionTranslation).filter(PositionTranslation.position_ru == key).first()
    if row:
        row.position_kk = kk
    else:
        row = PositionTranslation(position_ru=key, position_kk=kk)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- Начальное наполнение справочника должностей (типовые должности подписанта) ---
# Справочник один на модуль: и должности работников, и должности подписанта. Бухгалтер
# не обязан знать казахский — типовые пары идут из коробки, остальные накапливаются.
SEED_POSITIONS = [
    ("Директор", "Директор"),
    ("Генеральный директор", "Бас директор"),
    ("Исполнительный директор", "Атқарушы директор"),
    ("Заместитель директора", "Директордың орынбасары"),
    ("Президент", "Президент"),
    ("Управляющий", "Басқарушы"),
    ("Индивидуальный предприниматель", "Жеке кәсіпкер"),
]


def seed_positions(db: Session) -> None:
    """Идемпотентно засеять справочник стартовыми парами. Существующие пары не трогаем.
    Гонку между воркерами (uq_position_ru) гасим откатом — норм, кто-то уже засеял."""
    added = False
    for ru, kk in SEED_POSITIONS:
        key = _norm_ru(ru)
        exists = db.query(PositionTranslation).filter(PositionTranslation.position_ru == key).first()
        if exists is None:
            db.add(PositionTranslation(position_ru=key, position_kk=kk))
            added = True
    if not added:
        return
    try:
        db.commit()
    except IntegrityError:
        db.rollback()   # параллельный воркер успел засеять — это нормально
