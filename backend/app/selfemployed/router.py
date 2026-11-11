"""API модуля «Договор с самозанятым» — STATELESS генерация документа.

Договор собирается из данных запроса в памяти: в БД ничего не пишется, ИИН и ФИО
не попадают в логи и в URL (приходят только в теле запроса) — то же правило, что
в кадровом модуле.

Доступ закрыт сервисом `selfemployed` через `require_service` — тот же механизм,
которым закрыты кадровый модуль и помогайка 101.04. Роли у сервиса пусты: его
видит только администратор. Открыть сотрудникам — выдать роль на экране
«Доступы», правка кода для этого не нужна.
"""
from io import BytesIO
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.personnel.helpers.iin import is_valid_bin, is_valid_iin, parse_iin
from app.personnel.schemas import (
    BinCheckRequest, BinCheckResponse, IinCheckRequest, IinCheckResponse,
)
from app.selfemployed.builder import check, filename, render
from app.selfemployed.profiles import ORDER, PROFILES
from app.selfemployed.schemas import CheckResponse, ContractRequest, OkedInfo
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "selfemployed"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/api/selfemployed", tags=["selfemployed"])


@router.get("/okeds", response_model=List[OkedInfo])
async def list_okeds(_user: User = Depends(require_service(SERVICE_CODE))):
    """Справочник видов деятельности в порядке ORDER — источник для селекта формы."""
    return [
        OkedInfo(
            code=PROFILES[code]["code"],
            name=PROFILES[code]["name"],
            kind=PROFILES[code]["kind"],
            title=PROFILES[code]["title"],
            default_subject=PROFILES[code]["default_subject"],
            notice_days=PROFILES[code]["notice_days"],
        )
        for code in ORDER
    ]


@router.post("/validate/iin", response_model=IinCheckResponse)
async def validate_iin(
    data: IinCheckRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Проверка ИИН хелпером кадрового модуля (контрольная сумма + дата рождения).

    Свой эндпоинт, а не вызов /personnel/validate/iin: тот закрыт сервисом `hr`,
    и у сотрудника с доступом только к договору он отдал бы 403. Хелпер — общий.
    ИИН приходит только в теле запроса (правило о персданных)."""
    info = parse_iin(data.iin)
    return IinCheckResponse(
        valid=is_valid_iin(data.iin),
        birth_date=info.birth_date if info else None,
        gender=info.gender if info else None,
        warnings=[],
    )


@router.post("/validate/bin", response_model=BinCheckResponse)
async def validate_bin(
    data: BinCheckRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Проверка БИН/ИИН заказчика (длина + контрольная сумма)."""
    return BinCheckResponse(valid=is_valid_bin(data.bin))


@router.post("/check", response_model=CheckResponse)
async def check_contract(
    data: ContractRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Предупреждения по данным формы (предел 300 МРП, даты, ИИН/БИН, «___» в предмете).
    Генерацию не блокируют — форма показывает их жёлтым блоком."""
    return CheckResponse(warnings=check(data.model_dump()))


@router.post("/generate")
async def generate_contract(
    data: ContractRequest,
    _user: User = Depends(require_service(SERVICE_CODE)),
):
    """Договор .docx по данным формы. Ничего не сохраняется."""
    payload = data.model_dump()
    document = BytesIO(render(payload))
    # RFC 5987 — имя файла на кириллице.
    disposition = f"attachment; filename*=UTF-8''{quote(filename(payload))}"
    return StreamingResponse(
        document, media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )
