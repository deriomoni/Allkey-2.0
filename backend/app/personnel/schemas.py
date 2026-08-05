"""Pydantic schemas for the personnel module."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class IinCheckRequest(BaseModel):
    iin: str
    birth_date: Optional[date] = None   # optional cross-check from the form
    gender: Optional[str] = None        # "male" | "female"


class IinCheckResponse(BaseModel):
    valid: bool
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    warnings: List[str] = []


class BinCheckRequest(BaseModel):
    bin: str


class BinCheckResponse(BaseModel):
    valid: bool


class ZayavlenieVychetyRequest(BaseModel):
    deductions: List[str]               # keys: base_30_mrp | social_payments | social_882 | social_5000
    apply_from: Optional[date] = None   # по умолчанию — дата начала работы


class RatesResponse(BaseModel):
    effective_from: date
    effective_to: Optional[date] = None
    mrp: int
    mzp: int
    ipn_rate: float
    base_deduction_mrp: int
    opv_rate: float
    opvr_rate: float
    so_rate: float
    vosms_rate: float
    oosms_rate: float
    sn_rate: float
    unified_payment_rate: float


# ============================ CRUD schemas ============================
# PII rule: ИИН and document numbers travel only in request/response BODIES,
# never in path or query parameters (ТЗ §9).

class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Company ---------------------------------------------------------

class CompanyBase(BaseModel):
    name_ru: str
    name_kk: str = ""
    bin: str
    city: str = ""
    legal_address: str = ""
    actual_address: str = ""
    director_fio_ru: str = ""
    director_fio_kk: str = ""
    director_gender: str = "male"
    signatory_position: str = "Директор"
    acts_on_basis: str = "Устава"
    state_registration_date: Optional[date] = None
    bank: str = ""
    iik: str = ""
    bik: str = ""
    header_requisites: str = ""
    logo_path: str = ""


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    # All optional — partial update.
    name_ru: Optional[str] = None
    name_kk: Optional[str] = None
    bin: Optional[str] = None
    city: Optional[str] = None
    legal_address: Optional[str] = None
    actual_address: Optional[str] = None
    director_fio_ru: Optional[str] = None
    director_fio_kk: Optional[str] = None
    director_gender: Optional[str] = None
    signatory_position: Optional[str] = None
    acts_on_basis: Optional[str] = None
    state_registration_date: Optional[date] = None
    bank: Optional[str] = None
    iik: Optional[str] = None
    bik: Optional[str] = None
    header_requisites: Optional[str] = None
    logo_path: Optional[str] = None


class CompanyResponse(_ORMModel, CompanyBase):
    id: int
    created_at: Optional[datetime] = None


# --- Employee --------------------------------------------------------

class EmployeeBase(BaseModel):
    last_name: str
    first_name: str
    middle_name: str = ""
    iin: str
    document_type: str = "id_card"
    document_number: str = ""
    document_issued_by: str = ""
    document_issue_date: Optional[date] = None
    registration_address: str = ""
    actual_address: str = ""
    phone: str = ""
    email: str = ""
    birth_date: Optional[date] = None
    gender: str = ""
    iban: str = ""
    citizenship: str = "Республики Казахстан"
    fio_genitive_override: Optional[str] = None
    fio_dative_override: Optional[str] = None
    fio_accusative_override: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    iin: Optional[str] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    document_issued_by: Optional[str] = None
    document_issue_date: Optional[date] = None
    registration_address: Optional[str] = None
    actual_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    iban: Optional[str] = None
    citizenship: Optional[str] = None
    fio_genitive_override: Optional[str] = None
    fio_dative_override: Optional[str] = None
    fio_accusative_override: Optional[str] = None


class EmployeeResponse(_ORMModel, EmployeeBase):
    id: int
    created_at: Optional[datetime] = None
    warnings: List[str] = []


# --- Employment ------------------------------------------------------

class EmploymentBase(BaseModel):
    company_id: int
    employee_id: int
    position_ru: str
    position_kk: str = ""
    department: str = ""
    contract_type: str = "indefinite"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    probation_months: int = 0
    salary: Decimal = Decimal(0)
    currency: str = "KZT"
    allowances: str = ""
    rate: Decimal = Decimal(1)
    salary_words_override: Optional[str] = None
    hours_per_day: Optional[Decimal] = None
    hours_per_week: Optional[Decimal] = None
    work_time_from: str = "09:00"
    work_time_to: str = "18:00"
    lunch_from: str = "13:00"
    lunch_to: str = "14:00"
    days_off: str = "суббота, воскресенье"
    vacation_days: int = 24
    material_liability: bool = False
    confidentiality: bool = False
    ipn_deduction: str = "base_30_mrp"
    contract_number: str = ""
    contract_date: Optional[date] = None
    order_number: str = ""
    order_date: Optional[date] = None
    application_date: Optional[date] = None


class EmploymentCreate(EmploymentBase):
    pass


class EmploymentUpdate(BaseModel):
    position_ru: Optional[str] = None
    position_kk: Optional[str] = None
    department: Optional[str] = None
    contract_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    probation_months: Optional[int] = None
    salary: Optional[Decimal] = None
    currency: Optional[str] = None
    allowances: Optional[str] = None
    rate: Optional[Decimal] = None
    salary_words_override: Optional[str] = None
    hours_per_day: Optional[Decimal] = None
    hours_per_week: Optional[Decimal] = None
    work_time_from: Optional[str] = None
    work_time_to: Optional[str] = None
    lunch_from: Optional[str] = None
    lunch_to: Optional[str] = None
    days_off: Optional[str] = None
    vacation_days: Optional[int] = None
    material_liability: Optional[bool] = None
    confidentiality: Optional[bool] = None
    ipn_deduction: Optional[str] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    order_number: Optional[str] = None
    order_date: Optional[date] = None
    application_date: Optional[date] = None


class EmploymentResponse(_ORMModel, EmploymentBase):
    id: int
    created_at: Optional[datetime] = None
    warnings: List[str] = []


# --- Document preview -------------------------------------------------

class PrikazPreviewResponse(BaseModel):
    context: dict
    editable: dict  # {"employee": {...ФИО падежи}, "employment": {position_ru, salary_words_ru}}
