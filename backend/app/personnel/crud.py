"""CRUD for Company / Employee / Employment (ТЗ §5, §8).

PII rule (ТЗ §9): ИИН and document numbers travel only in request/response
BODIES — never in path or query parameters — and are never written to the
application log. All lookups use internal integer ids.

Validation split (ТЗ §11):
  * hard (400) — a *present* ИИН/БИН that fails its checksum;
  * soft (returned as `warnings`) — salary below МЗП at full rate, probation > 3
    months, start-before-contract date, birth-date/gender mismatch with the ИИН.
Empty ИИН/БИН is allowed so partial drafts can be saved (data arrives piecemeal).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.personnel import schemas as s
from app.personnel.helpers.iin import is_valid_iin, is_valid_bin
from app.personnel.helpers.validation import (
    validate_salary, validate_probation, validate_dates, validate_iin_matches,
)
from app.personnel.models import Company, Employee, Employment
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "hr"

crud_router = APIRouter(prefix="/personnel", tags=["personnel-crud"])


# ------------------------------ helpers ------------------------------

def _require_valid_bin(bin_value: str) -> None:
    if bin_value and not is_valid_bin(bin_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный БИН")


def _require_valid_iin(iin_value: str) -> None:
    if iin_value and not is_valid_iin(iin_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный ИИН")


def _employee_warnings(emp: Employee) -> List[str]:
    return validate_iin_matches(emp.iin, emp.birth_date, emp.gender)


def _employment_warnings(e: Employment) -> List[str]:
    warnings: List[str] = []
    if e.salary is not None:
        rate = float(e.rate) if e.rate is not None else 1.0
        warnings += validate_salary(e.salary, rate)
    warnings += validate_probation(e.probation_months or 0)
    if e.start_date and e.contract_date:
        warnings += validate_dates(e.start_date, e.contract_date)
    return warnings


def _get_or_404(db: Session, model, obj_id: int, name: str):
    obj = db.query(model).filter(model.id == obj_id).first()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} не найден(а)")
    return obj


def _apply(obj, data) -> None:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


# ------------------------------ companies ------------------------------

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
    return _get_or_404(db, Company, company_id, "Компания")


@crud_router.put("/companies/{company_id}", response_model=s.CompanyResponse)
async def update_company(company_id: int, data: s.CompanyUpdate, db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    company = _get_or_404(db, Company, company_id, "Компания")
    if data.bin is not None:
        _require_valid_bin(data.bin)
    _apply(company, data)
    db.commit()
    db.refresh(company)
    return company


# ------------------------------ employees ------------------------------

def _employee_response(emp: Employee) -> s.EmployeeResponse:
    resp = s.EmployeeResponse.model_validate(emp)
    resp.warnings = _employee_warnings(emp)
    return resp


@crud_router.post("/employees", response_model=s.EmployeeResponse)
async def create_employee(data: s.EmployeeCreate, db: Session = Depends(get_db),
                          _u: User = Depends(require_service(SERVICE_CODE))):
    _require_valid_iin(data.iin)
    employee = Employee(**data.model_dump())
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return _employee_response(employee)


@crud_router.get("/employees", response_model=List[s.EmployeeResponse])
async def list_employees(db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    return db.query(Employee).order_by(Employee.last_name, Employee.first_name).all()


@crud_router.get("/employees/{employee_id}", response_model=s.EmployeeResponse)
async def get_employee(employee_id: int, db: Session = Depends(get_db),
                       _u: User = Depends(require_service(SERVICE_CODE))):
    return _employee_response(_get_or_404(db, Employee, employee_id, "Работник"))


@crud_router.put("/employees/{employee_id}", response_model=s.EmployeeResponse)
async def update_employee(employee_id: int, data: s.EmployeeUpdate, db: Session = Depends(get_db),
                          _u: User = Depends(require_service(SERVICE_CODE))):
    employee = _get_or_404(db, Employee, employee_id, "Работник")
    if data.iin is not None:
        _require_valid_iin(data.iin)
    _apply(employee, data)
    db.commit()
    db.refresh(employee)
    return _employee_response(employee)


# ------------------------------ employments ------------------------------

def _employment_response(e: Employment) -> s.EmploymentResponse:
    resp = s.EmploymentResponse.model_validate(e)
    resp.warnings = _employment_warnings(e)
    return resp


@crud_router.post("/employments", response_model=s.EmploymentResponse)
async def create_employment(data: s.EmploymentCreate, db: Session = Depends(get_db),
                            _u: User = Depends(require_service(SERVICE_CODE))):
    _get_or_404(db, Company, data.company_id, "Компания")
    _get_or_404(db, Employee, data.employee_id, "Работник")
    employment = Employment(**data.model_dump())
    db.add(employment)
    db.commit()
    db.refresh(employment)
    return _employment_response(employment)


@crud_router.get("/employments", response_model=List[s.EmploymentResponse])
async def list_employments(company_id: int | None = None, employee_id: int | None = None,
                           db: Session = Depends(get_db),
                           _u: User = Depends(require_service(SERVICE_CODE))):
    query = db.query(Employment)
    if company_id is not None:
        query = query.filter(Employment.company_id == company_id)
    if employee_id is not None:
        query = query.filter(Employment.employee_id == employee_id)
    return [_employment_response(e) for e in query.order_by(Employment.id.desc()).all()]


@crud_router.get("/employments/{employment_id}", response_model=s.EmploymentResponse)
async def get_employment(employment_id: int, db: Session = Depends(get_db),
                         _u: User = Depends(require_service(SERVICE_CODE))):
    return _employment_response(_get_or_404(db, Employment, employment_id, "Приём на работу"))


@crud_router.put("/employments/{employment_id}", response_model=s.EmploymentResponse)
async def update_employment(employment_id: int, data: s.EmploymentUpdate, db: Session = Depends(get_db),
                            _u: User = Depends(require_service(SERVICE_CODE))):
    employment = _get_or_404(db, Employment, employment_id, "Приём на работу")
    _apply(employment, data)
    db.commit()
    db.refresh(employment)
    return _employment_response(employment)
