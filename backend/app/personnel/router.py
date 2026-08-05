"""Personnel module API.

Foundation endpoints for this tranche: current payroll rates and ИИН/БИН
validation wired to the helpers. All endpoints are gated by the `hr` service in
the registry (visible to employee + admin), matching how other modules gate
access via `require_service`.
"""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.personnel.context import (
    build_order_context, build_deduction_application_context, build_prikaz_preview,
    DEDUCTION_TEXTS,
)
from app.personnel.generator import render_template, output_filename
from app.personnel.helpers.iin import is_valid_iin, is_valid_bin, parse_iin
from app.personnel.helpers.validation import validate_iin_matches
from app.personnel.models import Employment
from app.personnel.rates import get_rates
from app.personnel.schemas import (
    IinCheckRequest, IinCheckResponse,
    BinCheckRequest, BinCheckResponse,
    RatesResponse, ZayavlenieVychetyRequest, PrikazPreviewResponse,
)
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "hr"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/personnel", tags=["personnel"])


def _docx_response(document, filename: str) -> StreamingResponse:
    # RFC 5987 for the non-ASCII (Cyrillic) filename.
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        document, media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )


def _get_employment_or_404(db: Session, employment_id: int) -> Employment:
    employment = db.query(Employment).filter(Employment.id == employment_id).first()
    if employment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Приём на работу не найден")
    return employment


@router.get("/rates", response_model=RatesResponse)
async def current_rates(
    on: date | None = None,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Payroll rates in force on `on` (default: today). Feeds the calculator."""
    r = get_rates(on)
    return RatesResponse(
        effective_from=r.effective_from,
        effective_to=r.effective_to,
        mrp=r.mrp,
        mzp=r.mzp,
        ipn_rate=r.ipn_rate,
        base_deduction_mrp=r.base_deduction_mrp,
        opv_rate=r.opv_rate,
        opvr_rate=r.opvr_rate,
        so_rate=r.so_rate,
        vosms_rate=r.vosms_rate,
        oosms_rate=r.oosms_rate,
        sn_rate=r.sn_rate,
        unified_payment_rate=r.unified_payment_rate,
    )


@router.post("/validate/iin", response_model=IinCheckResponse)
async def validate_iin(
    data: IinCheckRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Validate an ИИН and decode birth date / gender, warning on mismatches."""
    valid = is_valid_iin(data.iin)
    info = parse_iin(data.iin)
    warnings = validate_iin_matches(data.iin, data.birth_date, data.gender) if valid else []
    return IinCheckResponse(
        valid=valid,
        birth_date=info.birth_date if info else None,
        gender=info.gender if info else None,
        warnings=warnings,
    )


@router.post("/validate/bin", response_model=BinCheckResponse)
async def validate_bin(
    data: BinCheckRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Validate a БИН (length + checksum)."""
    return BinCheckResponse(valid=is_valid_bin(data.bin))


@router.get("/employments/{employment_id}/documents/prikaz/preview", response_model=PrikazPreviewResponse)
async def prikaz_preview(
    employment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_service(SERVICE_CODE)),
):
    """Editable-fields preview for the form: full rendered context + the ФИО
    declensions that are editable and persisted on the employee card (§6, §8)."""
    employment = _get_employment_or_404(db, employment_id)
    preview = build_prikaz_preview(
        employment.company, employment.employee, employment,
        hr_responsible_fio=user.full_name,
    )
    return PrikazPreviewResponse(**preview)


@router.get("/employments/{employment_id}/documents/prikaz")
async def generate_prikaz(
    employment_id: int,
    hr_responsible_fio: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_service(SERVICE_CODE)),
):
    """Generate the «Приказ о приёме на работу» .docx for an employment (§4.4).

    Vertical slice of the docx engine: loads the employment with its company and
    employee, builds the nested context and streams the rendered document.
    """
    employment = _get_employment_or_404(db, employment_id)
    employee = employment.employee
    context = build_order_context(
        employment.company, employee, employment,
        hr_responsible_fio=hr_responsible_fio or user.full_name,
    )
    document = render_template("prikaz_o_prieme.docx", context)
    filename = output_filename(
        employee.last_name, employee.first_name, employee.middle_name or "",
        "ПриказПриём", employment.order_date,
    )
    return _docx_response(document, filename)


@router.post("/employments/{employment_id}/documents/zayavlenie-vychety")
async def generate_zayavlenie_vychety(
    employment_id: int,
    data: ZayavlenieVychetyRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Generate the «Заявление о применении налоговых вычетов» .docx (§4.5).

    Deductions are an ordered selection of known keys; `apply_from` defaults to
    the employment start date, the application date to the recorded заявление date.
    """
    unknown = [k for k in data.deductions if k not in DEDUCTION_TEXTS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестные виды вычета: {', '.join(unknown)}",
        )

    employment = _get_employment_or_404(db, employment_id)
    employee = employment.employee
    apply_from = data.apply_from or employment.start_date
    context = build_deduction_application_context(
        employment.company, employee, data.deductions,
        apply_from=apply_from,
        application_date=employment.application_date or apply_from,
    )
    document = render_template("zayavlenie_vychety_ipn.docx", context)
    filename = output_filename(
        employee.last_name, employee.first_name, employee.middle_name or "",
        "ЗаявлениеВычеты", employment.application_date,
    )
    return _docx_response(document, filename)
