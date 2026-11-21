"""API `/api/ops/*` (этап A). Доступ решает OpsGateMiddleware по ROUTE_PERMISSIONS;
`require_ops_admin` в каждом обработчике — вторая линия обороны.

Поиск по реестру делается на клиенте: названия компаний не должны попадать в URL,
а значит и в access-логи.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.operations.access import effective_roles, filter_fields, is_ops_admin, list_admins, require_ops_admin
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, OpsCompanyReport
from app.operations.reports_import import commit_rows, match_rows, parse_workbook
from app.operations.sync import sync_companies
from app.users.models import User

router = APIRouter(prefix="/api/ops", tags=["ops"])

DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/{}"
MAX_UPLOAD = 10 * 1024 * 1024


def _iso(v) -> Optional[str]:
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


def _drive_url(folder_id: Optional[str]) -> Optional[str]:
    return DRIVE_FOLDER_URL.format(folder_id) if folder_id else None


def _list_item(c: OpsCompany) -> dict:
    resp = c.responsible_json or {}
    accountant = (c.card_json or {}).get("accountant") or ""
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "name_official": bool(str((c.card_json or {}).get("name") or "").strip()),
        "legal_name": c.legal_name,
        "bin": c.bin,
        "aliases": c.aliases or [],
        "folder_name": c.drive_folder_name,
        "tax_regime": c.tax_regime,
        "vat_payer": c.vat_payer,
        "responsible": (resp.get("name") or "").strip() or accountant.strip() or None,
        "active": c.active,
        "missing_in_repo": c.missing_in_repo,
        "drive_url": _drive_url(c.drive_root_folder_id),
    }


@router.get("/companies", name="ops_list_companies")
def list_companies(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    roles = effective_roles(db, user)
    items = db.query(OpsCompany).order_by(OpsCompany.active.desc(), OpsCompany.name).all()
    return {"items": [filter_fields(_list_item(c), roles) for c in items]}


@router.get("/companies/{company_id}", name="ops_get_company")
def get_company(company_id: int, user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    c = db.query(OpsCompany).filter(OpsCompany.id == company_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Not Found")
    reports = (
        db.query(OpsCompanyReport)
        .filter(OpsCompanyReport.company_id == c.id)
        .order_by(OpsCompanyReport.form, OpsCompanyReport.period)
        .all()
    )
    data = _list_item(c) | {
        "card": c.card_json,
        "onec": {
            "kind": c.onec_kind, "url": c.onec_url, "login": c.onec_login, "note": c.onec_note,
            "run_on": c.run_on, "closed_through": _iso(c.closed_through),
        },
        "inactive_reason": c.inactive_reason,
        "inactive_since": _iso(c.inactive_since),
        "drive": {
            "folder_name": c.drive_folder_name,
            "root_url": _drive_url(c.drive_root_folder_id),
            "agent_url": _drive_url(c.drive_agent_folder_id),
        },
        "reports": [
            {
                "id": r.id, "form": r.form, "period": r.period, "status": r.status,
                "raw_value": r.raw_value, "source": r.source,
                "evidence_url": f"https://drive.google.com/file/d/{r.evidence_drive_file_id}/view"
                if r.evidence_drive_file_id else None,
                "updated_at": _iso(r.updated_at),
            }
            for r in reports
        ],
        "synced_at": _iso(c.synced_at),
    }
    return filter_fields(data, effective_roles(db, user))


@router.post("/companies/sync", name="ops_sync_companies")
def sync(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    return sync_companies(db).as_dict()


@router.get("/status", name="ops_sync_status")
def status(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    total = db.query(func.count(OpsCompany.id)).scalar() or 0
    active = db.query(func.count(OpsCompany.id)).filter(OpsCompany.active.is_(True)).scalar() or 0
    last = db.query(func.max(OpsCompany.synced_at)).scalar()
    return {
        "total": total, "active": active, "inactive": total - active,
        "last_synced_at": _iso(last),
        "repo_configured": bool((get_ops_settings().arty_ops_path or "").strip()),
    }


@router.get("/admins", name="ops_list_admins")
def admins(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    """Кто сейчас имеет роль admin модуля — для блока в «Настройках»."""
    s = get_ops_settings()
    return {
        "items": list_admins(db),
        "env_admin_user_id": s.ops_admin_user_id,
        "visible_to_non_admin": s.ops_registry_visible_to_non_admin,
    }


@router.post("/reports/import/preview", name="ops_reports_import_preview")
async def import_preview(
    file: UploadFile = File(...), user: User = Depends(require_ops_admin), db: Session = Depends(get_db)
):
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Файл больше 10 МБ")
    try:
        parsed = parse_workbook(content)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл как xlsx")
    parsed["rows"] = match_rows(db, parsed["rows"])
    parsed["companies"] = [
        {"id": c.id, "name": c.name, "active": c.active}
        for c in db.query(OpsCompany).order_by(OpsCompany.name).all()
    ]
    return parsed


class CommitCell(BaseModel):
    period: str
    raw: Optional[str] = None
    status: str


class CommitRow(BaseModel):
    company_id: int
    form: str
    cells: List[CommitCell]


class CommitBody(BaseModel):
    rows: List[CommitRow]


@router.post("/reports/import/commit", name="ops_reports_import_commit")
def import_commit(body: CommitBody, user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    return commit_rows(db, [r.model_dump() for r in body.rows])


@router.get("/ui/bundle.js", name="ops_ui_bundle")
def ui_bundle(user: User = Depends(require_ops_admin)):
    """Отдельный бандл фронта модуля: отдаётся только admin (через тот же гейт)."""
    p = Path(get_ops_settings().ops_ui_bundle_path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(
        content=p.read_bytes(), media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


# --- Нейтральная точка для основной сборки: какие доп. разделы показать пользователю.
# Для всех, кроме admin модуля, — пустой список; основная сборка о модуле не знает.
ext_router = APIRouter(prefix="/users", tags=["users"])


@ext_router.get("/me/extensions")
def my_extensions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_ops_admin(db, user):
        return []
    return [{
        "key": "ops", "title": "Компании", "path": "/x/ops", "bundle": "/api/ops/ui/bundle.js",
        # Бандл умеет рисовать блок для страницы «Настройки» (список admin модуля).
        "settings": True,
    }]
