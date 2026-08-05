"""Personnel module API.

Foundation endpoints for this tranche: current payroll rates and ИИН/БИН
validation wired to the helpers. All endpoints are gated by the `hr` service in
the registry (visible to employee + admin), matching how other modules gate
access via `require_service`.
"""
from datetime import date

from fastapi import APIRouter, Depends

from app.personnel.helpers.iin import is_valid_iin, is_valid_bin, parse_iin
from app.personnel.helpers.validation import validate_iin_matches
from app.personnel.rates import get_rates
from app.personnel.schemas import (
    IinCheckRequest, IinCheckResponse,
    BinCheckRequest, BinCheckResponse,
    RatesResponse,
)
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "hr"

router = APIRouter(prefix="/personnel", tags=["personnel"])


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
