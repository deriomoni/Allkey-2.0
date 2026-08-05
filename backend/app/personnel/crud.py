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

from app.database import get_db
from app.personnel import schemas as s
from app.personnel.helpers.iin import is_valid_bin
from app.personnel.models import Company
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
