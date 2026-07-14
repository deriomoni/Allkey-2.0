import uuid
import time
import asyncio
import logging
import json
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from typing import Dict, Optional
from io import BytesIO
from pathlib import Path

from app.users.models import User
from app.services.dependencies import require_service
from app.reconciliation.schemas import (
    UploadResponse, PreviewRequest, PreviewResponse,
    Case1Settings, Case2Settings, Case3Settings, ReconciliationResult
)
from app.reconciliation.excel_parser import ExcelParser, ExcelParseError
from app.reconciliation.case1_service import Case1Service
from app.reconciliation.case2_service import Case2Service
from app.reconciliation.case3_service import Case3Service
from app.utils.excel_export import ExcelExporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

# Filesystem-based session storage (shared across workers)
STORAGE_DIR = Path(os.getenv("SESSION_STORAGE_DIR", "/tmp/reconciliation_sessions"))
FILES_DIR = STORAGE_DIR / "files"
RESULTS_DIR = STORAGE_DIR / "results"

FILE_TTL_SECONDS = 10 * 60      # 10 min
RESULT_TTL_SECONDS = 30 * 60    # 30 min
CLEANUP_INTERVAL_SECONDS = 300  # run cleanup every 5 min

# Upload validation
MAX_UPLOAD_BYTES = 20 * 1024 * 1024      # 20 MB
ALLOWED_UPLOAD_EXTENSIONS = {".xls", ".xlsx"}

# Ensure storage dirs exist
FILES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _validate_upload(file: UploadFile, content: bytes):
    """Reject non-Excel files and files exceeding the size limit."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только файлы Excel"
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Файл слишком большой (максимум 20 МБ)"
        )


def _check_owner(session_id: str, user: User, kind: str):
    """Ensure the session belongs to `user` (admin bypasses).

    kind: 'files' or 'results'. If the session has no meta yet, this is a no-op —
    the caller's own existence checks return the appropriate 404.
    """
    base = FILES_DIR if kind == "files" else RESULTS_DIR
    meta_path = base / session_id / "meta.json"
    if not meta_path.exists():
        return
    if user.role == "admin":
        return
    meta = json.loads(meta_path.read_text())
    if meta.get("user_id") != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к чужой сессии запрещён"
        )


def _save_files(session_id: str, files: Dict[str, bytes], user_id: int):
    """Save uploaded files to disk"""
    session_dir = FILES_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    meta = {"created_at": time.time(), "file_keys": list(files.keys()), "user_id": user_id}
    (session_dir / "meta.json").write_text(json.dumps(meta))
    for key, content in files.items():
        (session_dir / key).write_bytes(content)


def _get_file(session_id: str, file_key: str) -> Optional[bytes]:
    """Read a file from disk"""
    path = FILES_DIR / session_id / file_key
    if path.exists():
        return path.read_bytes()
    return None


def _get_all_files(session_id: str) -> Optional[Dict[str, bytes]]:
    """Read all files for a session from disk"""
    session_dir = FILES_DIR / session_id
    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    result = {}
    for key in meta["file_keys"]:
        path = session_dir / key
        if path.exists():
            result[key] = path.read_bytes()
    return result


def _session_exists(session_id: str) -> bool:
    """Check if a file session exists on disk"""
    return (FILES_DIR / session_id / "meta.json").exists()


def _delete_file_session(session_id: str):
    """Remove a file session from disk"""
    session_dir = FILES_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def _save_result(session_id: str, case_type: str, result: dict, user_id: int):
    """Save reconciliation result to disk"""
    session_dir = RESULTS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    meta = {"created_at": time.time(), "case_type": case_type, "user_id": user_id}
    (session_dir / "meta.json").write_text(json.dumps(meta))
    with open(session_dir / "result.json", "w", encoding="utf-8") as f:
        # default=str safely serializes any stray Decimal/date; amounts are
        # already plain floats and dates are strings, so numbers stay numeric.
        json.dump(result, f, ensure_ascii=False, default=str)


def _get_result(session_id: str) -> Optional[Dict]:
    """Read result from disk"""
    session_dir = RESULTS_DIR / session_id
    meta_path = session_dir / "meta.json"
    result_path = session_dir / "result.json"
    if not meta_path.exists() or not result_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    return {"case_type": meta["case_type"], "result": result, "created_at": meta["created_at"]}


def _result_exists(session_id: str) -> bool:
    """Check if a result session exists on disk"""
    return (RESULTS_DIR / session_id / "meta.json").exists()


def _delete_result_session(session_id: str):
    """Remove a result session from disk"""
    session_dir = RESULTS_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def _cleanup_expired():
    """Remove expired sessions from disk"""
    now = time.time()
    expired_files = 0
    expired_results = 0

    if FILES_DIR.exists():
        for session_dir in FILES_DIR.iterdir():
            meta_path = session_dir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                if now - meta.get("created_at", 0) > FILE_TTL_SECONDS:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    expired_files += 1

    if RESULTS_DIR.exists():
        for session_dir in RESULTS_DIR.iterdir():
            meta_path = session_dir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                if now - meta.get("created_at", 0) > RESULT_TTL_SECONDS:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    expired_results += 1

    if expired_files or expired_results:
        logger.info(f"Cleanup: removed {expired_files} file sessions, {expired_results} result sessions")


async def cleanup_task():
    """Background task that periodically cleans expired sessions"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        _cleanup_expired()


@router.post("/case1/upload", response_model=UploadResponse)
async def upload_case1_files(
    account_6010: UploadFile = File(...),
    esf_report: UploadFile = File(...),
    current_user: User = Depends(require_service("case1"))
):
    """Upload files for Case 1 reconciliation"""
    session_id = str(uuid.uuid4())

    account_6010_content = await account_6010.read()
    esf_content = await esf_report.read()
    _validate_upload(account_6010, account_6010_content)
    _validate_upload(esf_report, esf_content)

    _save_files(session_id, {
        'account_6010': account_6010_content,
        'esf_report': esf_content
    }, current_user.id)

    return UploadResponse(
        session_id=session_id,
        files={
            'account_6010': account_6010.filename,
            'esf_report': esf_report.filename
        },
        message="Files uploaded successfully"
    )


@router.post("/case1/preview", response_model=PreviewResponse)
async def preview_case1_file(
    request: PreviewRequest,
    current_user: User = Depends(require_service("case1"))
):
    """Preview a file from Case 1 upload"""
    if not _session_exists(request.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(request.session_id, current_user, "files")

    content = _get_file(request.session_id, request.file_key)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File key '{request.file_key}' not found"
        )

    parser = ExcelParser(content)

    try:
        preview = parser.get_preview(request.header_row, request.num_rows)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PreviewResponse(
        columns=preview['columns'],
        data=preview['data'],
        total_rows=preview['total_rows']
    )


@router.post("/case1/process", response_model=ReconciliationResult)
async def process_case1(
    settings: Case1Settings,
    current_user: User = Depends(require_service("case1"))
):
    """Process Case 1 reconciliation"""
    if not _session_exists(settings.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(settings.session_id, current_user, "files")

    session_files = _get_all_files(settings.session_id)

    service = Case1Service(
        account_6010_content=session_files['account_6010'],
        esf_content=session_files['esf_report'],
        account_6010_settings=settings.account_6010.model_dump(),
        esf_settings=settings.esf_report.model_dump()
    )

    try:
        result = service.reconcile()
    except (ExcelParseError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Store result on disk, then free file session
    _save_result(settings.session_id, 'case1', result, current_user.id)
    _delete_file_session(settings.session_id)

    return ReconciliationResult(**result)


@router.get("/case1/download/{session_id}")
async def download_case1_result(
    session_id: str,
    current_user: User = Depends(require_service("case1"))
):
    """Download Case 1 reconciliation result as Excel"""
    _check_owner(session_id, current_user, "results")

    stored = _get_result(session_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результат не найден или истёк. Выполните сверку заново."
        )

    exporter = ExcelExporter(stored['result'], stored['case_type'])
    excel_content = exporter.export()

    # Free result after download
    _delete_result_session(session_id)

    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=reconciliation_case1_{session_id[:8]}.xlsx"
        }
    )


@router.post("/case2/upload", response_model=UploadResponse)
async def upload_case2_files(
    our_act: UploadFile = File(...),
    counterparty_act: UploadFile = File(...),
    current_user: User = Depends(require_service("case2"))
):
    """Upload files for Case 2 reconciliation"""
    session_id = str(uuid.uuid4())

    our_act_content = await our_act.read()
    counterparty_act_content = await counterparty_act.read()
    _validate_upload(our_act, our_act_content)
    _validate_upload(counterparty_act, counterparty_act_content)

    _save_files(session_id, {
        'our_act': our_act_content,
        'counterparty_act': counterparty_act_content
    }, current_user.id)

    return UploadResponse(
        session_id=session_id,
        files={
            'our_act': our_act.filename,
            'counterparty_act': counterparty_act.filename
        },
        message="Files uploaded successfully"
    )


@router.post("/case2/preview", response_model=PreviewResponse)
async def preview_case2_file(
    request: PreviewRequest,
    current_user: User = Depends(require_service("case2"))
):
    """Preview a file from Case 2 upload"""
    if not _session_exists(request.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(request.session_id, current_user, "files")

    content = _get_file(request.session_id, request.file_key)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File key '{request.file_key}' not found"
        )

    parser = ExcelParser(content)

    try:
        preview = parser.get_preview(request.header_row, request.num_rows)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PreviewResponse(
        columns=preview['columns'],
        data=preview['data'],
        total_rows=preview['total_rows']
    )


@router.post("/case2/process", response_model=ReconciliationResult)
async def process_case2(
    settings: Case2Settings,
    current_user: User = Depends(require_service("case2"))
):
    """Process Case 2 reconciliation"""
    if not _session_exists(settings.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(settings.session_id, current_user, "files")

    session_files = _get_all_files(settings.session_id)

    service = Case2Service(
        our_act_content=session_files['our_act'],
        counterparty_act_content=session_files['counterparty_act'],
        our_act_settings=settings.our_act.model_dump(),
        counterparty_act_settings=settings.counterparty_act.model_dump()
    )

    try:
        result = service.reconcile()
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    _save_result(settings.session_id, 'case2', result, current_user.id)
    _delete_file_session(settings.session_id)

    return ReconciliationResult(**result)


@router.get("/case2/download/{session_id}")
async def download_case2_result(
    session_id: str,
    current_user: User = Depends(require_service("case2"))
):
    """Download Case 2 reconciliation result as Excel"""
    _check_owner(session_id, current_user, "results")

    stored = _get_result(session_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результат не найден или истёк. Выполните сверку заново."
        )

    exporter = ExcelExporter(stored['result'], stored['case_type'])
    excel_content = exporter.export()

    _delete_result_session(session_id)

    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=reconciliation_case2_{session_id[:8]}.xlsx"
        }
    )


# ==================== Case 3: 3310 vs ESF ====================

@router.post("/case3/upload", response_model=UploadResponse)
async def upload_case3_files(
    account_3310: UploadFile = File(...),
    esf_report: UploadFile = File(...),
    current_user: User = Depends(require_service("case3"))
):
    """Upload files for Case 3 reconciliation"""
    session_id = str(uuid.uuid4())

    account_3310_content = await account_3310.read()
    esf_content = await esf_report.read()
    _validate_upload(account_3310, account_3310_content)
    _validate_upload(esf_report, esf_content)

    _save_files(session_id, {
        'account_3310': account_3310_content,
        'esf_report': esf_content
    }, current_user.id)

    return UploadResponse(
        session_id=session_id,
        files={
            'account_3310': account_3310.filename,
            'esf_report': esf_report.filename
        },
        message="Files uploaded successfully"
    )


@router.post("/case3/preview", response_model=PreviewResponse)
async def preview_case3_file(
    request: PreviewRequest,
    current_user: User = Depends(require_service("case3"))
):
    """Preview a file from Case 3 upload"""
    if not _session_exists(request.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(request.session_id, current_user, "files")

    content = _get_file(request.session_id, request.file_key)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File key '{request.file_key}' not found"
        )

    parser = ExcelParser(content)

    try:
        preview = parser.get_preview(request.header_row, request.num_rows)
    except ExcelParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PreviewResponse(
        columns=preview['columns'],
        data=preview['data'],
        total_rows=preview['total_rows']
    )


@router.post("/case3/process", response_model=ReconciliationResult)
async def process_case3(
    settings: Case3Settings,
    current_user: User = Depends(require_service("case3"))
):
    """Process Case 3 reconciliation"""
    if not _session_exists(settings.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сессия не найдена или истекла. Загрузите файлы заново."
        )

    _check_owner(settings.session_id, current_user, "files")

    session_files = _get_all_files(settings.session_id)

    service = Case3Service(
        account_3310_content=session_files['account_3310'],
        esf_content=session_files['esf_report'],
        account_3310_settings=settings.account_3310.model_dump(),
        esf_settings=settings.esf_report.model_dump()
    )

    try:
        result = service.reconcile()
    except (ExcelParseError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    _save_result(settings.session_id, 'case3', result, current_user.id)
    _delete_file_session(settings.session_id)

    return ReconciliationResult(**result)


@router.get("/case3/download/{session_id}")
async def download_case3_result(
    session_id: str,
    current_user: User = Depends(require_service("case3"))
):
    """Download Case 3 reconciliation result as Excel"""
    _check_owner(session_id, current_user, "results")

    stored = _get_result(session_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Результат не найден или истёк. Выполните сверку заново."
        )

    exporter = ExcelExporter(stored['result'], stored['case_type'])
    excel_content = exporter.export()

    _delete_result_session(session_id)

    return StreamingResponse(
        BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=reconciliation_case3_{session_id[:8]}.xlsx"
        }
    )
