"""Pydantic schemas for the personnel module."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


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
    # Manual Kazakh translations for the bilingual трудовой договор (proofread before sale).
    address_kz: str = ""
    signer_position_kz: str = ""
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
    address_kz: Optional[str] = None                # kk-реквизиты юрлица — заполняются в карточке
    signer_position_kz: Optional[str] = None
    state_registration_date: Optional[date] = None
    bank: Optional[str] = None
    iik: Optional[str] = None
    bik: Optional[str] = None
    header_requisites: Optional[str] = None
    logo_path: Optional[str] = None


class CompanyResponse(_ORMModel, CompanyBase):
    id: int
    created_at: Optional[datetime] = None


class PositionTranslationIn(BaseModel):
    """Пара «русская должность → казахская» для справочника (§4.2)."""
    position_ru: str
    position_kk: str = ""


class PositionTranslationOut(_ORMModel):
    position_ru: str
    position_kk: str


# --- Stateless input models (NOT stored; come in the request body) ----
# Employee/Employment carry third-party personal data and are never persisted —
# they live in the client's draft and arrive in the generation request body.

class EmployeeIn(BaseModel):
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    iin: str = ""
    document_type: str = "id_card"
    document_number: str = ""
    document_issued_by: str = ""
    document_issue_date: Optional[date] = None
    registration_address: str = ""
    actual_address: str = ""
    phone: str = ""
    email: str = ""
    birth_date: Optional[date] = None
    gender: str = "male"
    iban: str = ""
    citizenship: str = "Республики Казахстан"
    # Manual Kazakh translations for the bilingual трудовой договор.
    fio_full_kz: str = ""
    id_document_kz: str = ""
    # Manual declension edits — kept in the client draft, sent for this render only.
    fio_genitive_override: Optional[str] = None
    fio_dative_override: Optional[str] = None
    fio_accusative_override: Optional[str] = None


class EmploymentIn(BaseModel):
    position_ru: str = ""
    position_kk: str = ""              # = position_kz in the ТД context
    workplace: str = ""
    workplace_kz: str = ""
    conditions: str = "нормальными"   # характеристика условий труда (ru); kz из справочника
    department: str = ""
    contract_type: str = "indefinite"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    probation_months: int = 0
    salary: int = 0                   # оклад — только целые тенге (без копеек)
    salary_kind: str = "gross"        # gross (к начислению) | net (на руки) — меняет формулировки ТД, сумма как есть
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
    # Numbers are typed in by hand — there is no server-side sequential numbering.
    contract_number: str = ""
    contract_date: Optional[date] = None
    order_number: str = ""
    order_date: Optional[date] = None
    application_date: Optional[date] = None

    @field_validator("salary", mode="before")
    @classmethod
    def _salary_whole_tenge(cls, v):
        """Оклад указывается целыми тенге. Дробное значение отклоняется явно,
        а не усекается молча (тихая потеря данных хуже запрета)."""
        if v is None or v == "":
            return 0
        try:
            d = Decimal(str(v).replace(" ", "").replace("\xa0", "").replace(",", "."))
        except InvalidOperation:
            raise ValueError("Оклад должен быть числом в тенге.")
        if d != d.to_integral_value():
            raise ValueError("Оклад указывается целыми тенге, без копеек.")
        return int(d)

    @field_validator("salary_kind")
    @classmethod
    def _known_salary_kind(cls, v: str) -> str:
        if v not in ("gross", "net"):
            raise ValueError("salary_kind должен быть 'gross' (к начислению) или 'net' (на руки)")
        return v


# --- Generation request bodies (stateless) ----------------------------

class PrikazRequest(BaseModel):
    company: CompanyBase
    employee: EmployeeIn
    employment: EmploymentIn
    hr_responsible_fio: str = ""


class ZayavlenieVychetyRequest(BaseModel):
    company: CompanyBase
    employee: EmployeeIn
    employment: EmploymentIn
    deductions: List[str]               # keys: base_30_mrp | social_payments | social_882 | social_5000
    apply_from: Optional[date] = None   # по умолчанию — дата начала работы


class ContractIn(BaseModel):
    number: str = ""
    doc_date: Optional[date] = None
    kind: str = "indefinite"            # indefinite | fixed | task | substitute
    # fixed-term: срок считается из term_count + term_unit (term/term_kz — хелперами)
    term_count: Optional[int] = None
    term_unit: str = "year"             # year | month
    end_date: Optional[date] = None
    task: str = ""                      # task-kind: описание работы (ru)
    task_kz: str = ""                   # task-kind: описание работы (kz, вручную)
    confidential_years: str = "3"


class TrudovoyRequest(BaseModel):
    company: CompanyBase
    employee: EmployeeIn
    employment: EmploymentIn
    contract: ContractIn


class PrikazPreviewResponse(BaseModel):
    context: dict
    editable: dict          # {"employee": {...ФИО падежи}, "employment": {position_ru, salary_words_ru}}
    warnings: List[str] = []


# --- Document-package inputs (stateless, ТЗ §2/§8) --------------------

class InventoryItemIn(BaseModel):
    name: str = ""
    code: str = ""
    unit: str = ""
    qty: Decimal = Decimal(0)
    price: Decimal = Decimal(0)


class CommissionMemberIn(BaseModel):
    position: str = ""
    fio_short: str = ""


class PerechenPositionIn(BaseModel):
    name: str = ""
    reason: str = ""


class LiabilityIn(BaseModel):
    number: str = ""
    doc_date: Optional[date] = None


class NonCompeteIn(BaseModel):
    number: str = ""
    doc_date: Optional[date] = None
    term_noncompete: str = ""       # сроки — ПОЛЯ, не константы
    term_nonsolicit: str = ""
    term_confidential: str = ""
    territory: str = ""
    activity: str = ""
    competitors: str = ""
    penalty: str = ""


class ActIn(BaseModel):
    number: str = ""
    doc_date: Optional[date] = None
    basis: str = ""                       # свободное «Основание»: «приказ № 14 от …» (пусто → не выводится)
    notes: str = ""
    commission: List[CommissionMemberIn] = []


class PerechenIn(BaseModel):
    number: str = ""
    doc_date: Optional[date] = None
    responsible_fio: str = ""
    responsible_position: str = ""
    control: str = "оставляю за собой"
    positions: List[PerechenPositionIn] = []
    acquainted: List[CommissionMemberIn] = []


class PolicyIn(BaseModel):
    """Данные для приказа о назначении ответственного за ПД + Положения (§4.6)."""
    order_number: str = ""
    doc_date: Optional[date] = None
    responsible_fio: str = ""             # им.п. → склоняется в винительный
    responsible_position: str = ""        # им.п. → склоняется в винительный
    deadline: Optional[date] = None       # срок ознакомления
    control: str = "оставляю за собой"
    acquainted: List[CommissionMemberIn] = []


class RecipientIn(BaseModel):
    """Получатель ПД в согласии на обработку (банк, ОСМС, СФР и т.д.)."""
    name: str = ""
    bin: str = ""              # необязательно
    purpose: str = ""          # цель передачи
    scope: str = ""            # объём передаваемых данных


class SoglasieIn(BaseModel):
    """Согласие на сбор и обработку персональных данных (§4.7)."""
    doc_date: Optional[date] = None
    recipients: List[RecipientIn] = []
    cross_border: bool = False
    cross_border_countries: str = ""
    cross_border_purpose: str = ""
    responsible_position: str = ""
    responsible_fio: str = ""
    responsible_contacts: str = ""


class PackageRequest(BaseModel):
    company: CompanyBase
    employee: EmployeeIn
    employment: EmploymentIn
    hr_responsible_fio: str = ""
    documents: List[str]                        # td | prikaz | soglasie | zayavlenie | matotvet | akt | nekonkurencii
    deductions: List[str] = []                  # for zayavlenie
    apply_from: Optional[date] = None
    liability: Optional[LiabilityIn] = None     # for matotvet / akt basis
    noncompete: Optional[NonCompeteIn] = None   # for nekonkurencii / perechen terms
    act: Optional[ActIn] = None                 # for akt
    inventory: List[InventoryItemIn] = []       # for akt опись
    perechen: Optional[PerechenIn] = None       # for perechen (library one-off)
    contract: Optional[ContractIn] = None       # for trudovoy dogovor
    policy: Optional[PolicyIn] = None           # for polozhenie_pd / prikaz_pd (library one-off, §4.6)
    consent: Optional[SoglasieIn] = None        # for soglasie (согласие на обработку ПД, §4.7)


class InventoryColumn(BaseModel):
    index: int
    title: str
    samples: List[str] = []


class InventoryParseResponse(BaseModel):
    status: str = "parsed"                       # "parsed" | "needs_mapping"
    items: List[InventoryItemIn] = []
    columns: List[InventoryColumn] = []          # when needs_mapping: columns to map by hand
    header_row: Optional[int] = None
