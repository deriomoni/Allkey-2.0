"""API `/api/ops/*` (этап A). Доступ решает OpsGateMiddleware по ROUTE_PERMISSIONS;
`require_ops_admin` в каждом обработчике — вторая линия обороны.

Поиск по реестру делается на клиенте: названия компаний не должны попадать в URL,
а значит и в access-логи.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.operations.access import (
    company_visible, effective_roles, filter_fields, is_ops_admin, list_admins, list_staff, require_ops_admin,
    require_ops_user, sees_hidden, visible_companies,
)
from app.operations import companies_xlsx
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, OpsCompanyReport, OpsObligationFlag
from app.operations import obligations as obl
from app.operations import card_edit
from app.operations import staff_edits
from app.operations import kgd
from app.operations import cabinet_queue as cq
from app.operations.sync import sync_one
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


def _plan_forms(db: Session, ids=None) -> dict:
    """{company_id: {форма}} — строки плана (source=plan) на текущий год; «не требуется» не считается.
    Строки без года в периоде («не описан») тоже план этого года."""
    year = str(dt.date.today().year)
    q = db.query(OpsCompanyReport.company_id, OpsCompanyReport.form, OpsCompanyReport.period).filter(
        OpsCompanyReport.source == "plan", OpsCompanyReport.status != "not_required")
    if ids is not None:
        q = q.filter(OpsCompanyReport.company_id.in_(list(ids)))
    out: dict = {}
    for cid, form, period in q.all():
        p = str(period or "")
        if p.startswith(year) or not any(ch.isdigit() for ch in p[:4]):
            out.setdefault(cid, set()).add(form)
    return out


def _list_item(c: OpsCompany, plan: Optional[dict] = None) -> dict:
    """plan — {company_id: {форма}} из _plan_forms: тогда «Формы» = tax.forms ∪ план, и у живой компании без
    плана на текущий год — plan_missing («план не рассчитан»)."""
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
        "hidden": bool(c.hidden),
        "drive_url": _drive_url(c.drive_root_folder_id),
        "forms": companies_xlsx.merged_forms(c.card_json or {}, (plan or {}).get(c.id)) if plan is not None
        else companies_xlsx.card_forms(c.card_json or {}),
        "plan_missing": bool(plan is not None and c.active and not (plan or {}).get(c.id)),
        "vat_date": companies_xlsx.card_vat_date(c.card_json or {}),
    }


@router.get("/companies", name="ops_list_companies")
def list_companies(user: User = Depends(require_ops_user), db: Session = Depends(get_db)):
    roles = effective_roles(db, user)
    items = visible_companies(db, roles).order_by(OpsCompany.active.desc(), OpsCompany.name).all()
    ids = {c.id for c in items}
    suspected = {
        cid: n for cid, n in db.query(OpsObligationFlag.company_id, func.count(OpsObligationFlag.id))
        .filter(OpsObligationFlag.status == "suspected")
        .group_by(OpsObligationFlag.company_id).all() if cid in ids
    }
    plan = _plan_forms(db)
    return {"items": [filter_fields(_list_item(c, plan) | {"suspected_count": suspected.get(c.id, 0)}, roles)
                      for c in items]}


def _flag(f: OpsObligationFlag) -> dict:
    return {
        "idx": f.idx, "form": f.form, "status": f.status, "period": f.period,
        "trigger": f.trigger_json or [], "source": f.source, "raised_at": f.raised_at,
        "decided_by": f.decided_by, "decided_at": f.decided_at, "reason": f.reason,
    }


def _card_flag(c: OpsCompany, idx: int) -> dict:
    flags = (c.card_json or {}).get("obligation_flags") or []
    return flags[idx] if 0 <= idx < len(flags) and isinstance(flags[idx], dict) else {}


@router.get("/companies/{company_id}", name="ops_get_company")
def get_company(company_id: int, user: User = Depends(require_ops_user), db: Session = Depends(get_db)):
    roles = effective_roles(db, user)
    c = visible_companies(db, roles).filter(OpsCompany.id == company_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Not Found")
    reports = (
        db.query(OpsCompanyReport)
        .filter(OpsCompanyReport.company_id == c.id)
        .order_by(OpsCompanyReport.form, OpsCompanyReport.period)
        .all()
    )
    data = _list_item(c, _plan_forms(db, [c.id])) | {
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
        "staff_notes": (c.card_json or {}).get("staff_notes") or [],
        "profile": (c.card_json or {}).get("profile") or None,
        # блок cabinet: — последняя проверка кабинета налогоплательщика (пишет knp-watch); null — не заходили
        "cabinet": (c.card_json or {}).get("cabinet") or None,
        "profile_url": _drive_url((((c.card_json or {}).get("systems") or {}).get("drive") or {}).get("profile_folder_id")),
        "obligations": [
            _flag(f) | {"raised_by": _card_flag(c, f.idx).get("raised_by")} for f in db.query(OpsObligationFlag)
            .filter(OpsObligationFlag.company_id == c.id).order_by(OpsObligationFlag.idx).all()
        ],
    }
    q = cq.open_entry(db, c.id)
    data["cabinet_queue"] = cq.entry_dict(q) if q else None  # только admin (VISIBLE_FIELDS сотрудника его не содержит)
    if not sees_hidden(roles):
        # Сотруднику — без закрытой папки _agent (ТЗ: только владелец) и без признака «скрытая».
        data["drive"] = {k: v for k, v in data["drive"].items() if k != "agent_url"}
        card = json.loads(json.dumps(data.get("card") or {}, default=str))
        card.pop("hidden", None)
        card.pop("cabinet", None)  # блок «Кабинет налогоплательщика» сотруднику пока не показываем (владелец 24.11.2026)
        ((card.get("systems") or {}).get("drive") or {}).pop("agent_folder_id", None)
        data["card"] = card
    return filter_fields(data, roles)


class ObligationIn(BaseModel):
    form: str
    period: str
    trigger: List[str]


class DecisionIn(BaseModel):
    form: str
    period: str
    reason: Optional[str] = None


def _company_or_404(db: Session, company_id: int, user: Optional[User] = None) -> OpsCompany:
    c = db.query(OpsCompany).filter(OpsCompany.id == company_id).first()
    if not company_visible(c, effective_roles(db, user) if user else set()):
        raise HTTPException(status_code=404, detail="Not Found")
    return c


def _decision(db: Session, c: OpsCompany, fn) -> dict:
    try:
        sha = fn()
    except obl.ObligationError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    sync_one(db, c.slug)
    return {"ok": True, "commit": sha}


def _user_label(user: User) -> str:
    return user.email


@router.post("/companies/{company_id}/obligations", name="ops_obligation_create")
def obligation_create(company_id: int, body: ObligationIn, user: User = Depends(require_ops_user),
                      db: Session = Depends(get_db)):
    """Поднять флаг «подозрение». admin — любая форма; сотрудник — только STAFF_FLAG_FORMS, основание
    обязательно (проверяет raise_flag). Подтверждает/снимает только admin."""
    c = _company_or_404(db, company_id, user)
    if is_ops_admin(db, user):
        return _decision(db, c, lambda: obl.raise_flag(c.slug, body.form, body.period, body.trigger, _user_label(user)))
    if body.form.strip() not in STAFF_FLAG_FORMS:
        raise HTTPException(status_code=400, detail="Сотрудник может поставить флаг только по формам: "
                            + ", ".join(STAFF_FLAG_FORMS))
    return _decision(db, c, lambda: obl.raise_flag(c.slug, body.form.strip(), body.period, body.trigger,
                                                   _user_label(user), source="employee"))


STAFF_FLAG_FORMS = ("101.04", "328.00", "700.00", "отчёт участника Астана Хаб")


class OnecIn(BaseModel):
    url: Optional[str] = None
    kind: Optional[str] = None
    note: Optional[str] = None
    reason: str


@router.post("/companies/{company_id}/onec", name="ops_company_onec_update")
def company_onec_update(company_id: int, body: OnecIn, user: User = Depends(require_ops_user),
                        db: Session = Depends(get_db)):
    """Адрес базы 1С (url, kind, note) с причиной; кто/когда — в systems.onec.edited и в коммите."""
    c = _company_or_404(db, company_id, user)
    return _decision(db, c, lambda: staff_edits.set_onec(c.slug, body.url, body.kind, body.note, body.reason,
                                                          _user_label(user)))


class NoteIn(BaseModel):
    text: str
    form: Optional[str] = None
    period: Optional[str] = None


@router.post("/companies/{company_id}/notes", name="ops_company_note_add")
def company_note_add(company_id: int, body: NoteIn, user: User = Depends(require_ops_user),
                     db: Session = Depends(get_db)):
    """Заметка по компании или к строке формы (form/period) — в staff_notes карточки, с автором и датой."""
    c = _company_or_404(db, company_id, user)
    return _decision(db, c, lambda: staff_edits.add_note(c.slug, body.text, _user_label(user), body.form, body.period))


@router.post("/companies/{company_id}/obligations/{idx}/confirm", name="ops_obligation_confirm")
def obligation_confirm(company_id: int, idx: int, body: DecisionIn, user: User = Depends(require_ops_admin),
                       db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id, user)
    return _decision(db, c, lambda: obl.confirm_flag(c.slug, idx, body.form, body.period, _user_label(user)))


@router.post("/companies/{company_id}/obligations/{idx}/dismiss", name="ops_obligation_dismiss")
def obligation_dismiss(company_id: int, idx: int, body: DecisionIn, user: User = Depends(require_ops_admin),
                       db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id, user)
    return _decision(db, c, lambda: obl.dismiss_flag(c.slug, idx, body.form, body.period, body.reason or "",
                                                     _user_label(user)))


class HiddenIn(BaseModel):
    hidden: bool


@router.post("/companies/{company_id}/hidden", name="ops_company_set_hidden")
def company_set_hidden(company_id: int, body: HiddenIn, user: User = Depends(require_ops_admin),
                       db: Session = Depends(get_db)):
    """Переключатель «скрытая» (ТЗ 1.1 п. 9): правка hidden в client.yaml коммитом от системы."""
    c = _company_or_404(db, company_id, user)
    try:
        sha = card_edit.set_hidden(c.slug, body.hidden, _user_label(user))
    except obl.ObligationError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    c = sync_one(db, c.slug)
    return {"ok": True, "hidden": bool(c.hidden), "commit": sha}


class CabinetQueueIn(BaseModel):
    note: Optional[str] = None


class CabinetDoneIn(BaseModel):
    result: Optional[str] = None


@router.get("/cabinet-queue", name="ops_cabinet_queue_list")
def cabinet_queue_list(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    return {"items": [cq.entry_dict(e, c) for e, c in cq.open_entries(db)]}


@router.post("/companies/{company_id}/cabinet-queue", name="ops_cabinet_queue_add")
def cabinet_queue_add(company_id: int, body: CabinetQueueIn, user: User = Depends(require_ops_admin),
                      db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id, user)
    try:
        e, created = cq.enqueue(db, c, "manual", body.note, by=user.email)
    except cq.QueueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"ok": True, "created": created, "entry": cq.entry_dict(e)}


@router.post("/cabinet-queue/{entry_id}/done", name="ops_cabinet_queue_done")
def cabinet_queue_done(entry_id: int, body: CabinetDoneIn, user: User = Depends(require_ops_admin),
                       db: Session = Depends(get_db)):
    from app.operations.models import OpsCabinetQueue
    e = db.query(OpsCabinetQueue).filter(OpsCabinetQueue.id == entry_id).first()
    if e is None:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        cq.mark_done(db, e, by=user.email, result=body.result or "снято вручную")
    except cq.QueueError as err:
        raise HTTPException(status_code=409, detail=str(err))
    return {"ok": True, "entry": cq.entry_dict(e)}


@router.get("/kgd/check", name="ops_kgd_check")
def kgd_check(bin: str, user: User = Depends(require_ops_admin)):
    """API КГД «Сведения по контрагентам» по БИН/ИИН (только admin; БИН в access-логе маскируется)."""
    try:
        return kgd.check(bin)
    except kgd.KgdError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@router.post("/companies/sync", name="ops_sync_companies")
def sync(user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    return sync_companies(db).as_dict()


@router.get("/status", name="ops_sync_status")
def status(user: User = Depends(require_ops_user), db: Session = Depends(get_db)):
    roles = effective_roles(db, user)
    q = visible_companies(db, roles)
    total = q.count()
    active = q.filter(OpsCompany.active.is_(True)).count()
    last = db.query(func.max(OpsCompany.synced_at)).scalar()
    extra = {"hidden": db.query(OpsCompany).filter(OpsCompany.hidden.is_(True)).count()} if sees_hidden(roles) else {}
    return extra | {
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
        "staff": list_staff(db),
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


@router.get("/me", name="ops_me")
def ops_me(user: User = Depends(require_ops_user), db: Session = Depends(get_db)):
    """Роль в модуле — бандлу, чтобы не рисовать сотруднику недоступное (защита — на сервере)."""
    return {"role": "admin" if is_ops_admin(db, user) else "staff"}


class ExportIn(BaseModel):
    ids: List[int]


@router.post("/companies/export", name="ops_companies_export")
def companies_export(body: ExportIn, user: User = Depends(require_ops_user), db: Session = Depends(get_db)):
    """xlsx текущего отфильтрованного списка: клиент присылает id строк в порядке экрана. Отбор — через
    visible_companies: скрытые у не-admin не попадут ни при каких id. Id — в теле, не в адресе."""
    roles = effective_roles(db, user)
    ids = list(dict.fromkeys(body.ids))[:5000]
    found = {c.id: c for c in visible_companies(db, roles).filter(OpsCompany.id.in_(ids)).all()} if ids else {}
    plan = _plan_forms(db, found.keys())
    items = [filter_fields(_list_item(found[i], plan), roles) for i in ids if i in found]
    data = companies_xlsx.export_xlsx(items)
    name = f"companies-{dt.date.today().isoformat()}.xlsx"
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/companies/forms-import/preview", name="ops_forms_import_preview")
async def forms_import_preview(file: UploadFile = File(...), user: User = Depends(require_ops_admin),
                               db: Session = Depends(get_db)):
    """Шаг 1 импорта форм: разбор файла и план изменений. Ничего не пишет."""
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Файл больше 10 МБ")
    try:
        parsed = companies_xlsx.parse_xlsx(content)
    except obl.ObligationError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл как xlsx")
    plan = companies_xlsx.build_plan(db.query(OpsCompany).all(), parsed)
    plan["file_name"] = (file.filename or "")[:120]
    return plan


class FormsChange(BaseModel):
    company_id: int
    add: List[str] = []
    remove: List[str] = []


class FormsApplyIn(BaseModel):
    file_name: str = ""
    changes: List[FormsChange]
    companies_in_file: int = 0
    unmatched: int = 0
    discrepancies: int = 0
    blocked: int = 0


@router.post("/companies/forms-import/apply", name="ops_forms_import_apply")
def forms_import_apply(body: FormsApplyIn, user: User = Depends(require_ops_admin), db: Session = Depends(get_db)):
    """Шаг 2: применить изменения форм — коммит в prod-decisions клона, затем пересинхронизация карточек."""
    ids = [c.company_id for c in body.changes]
    slugs = {c.id: c.slug for c in db.query(OpsCompany).filter(OpsCompany.id.in_(ids)).all()} if ids else {}
    try:
        res = companies_xlsx.apply_plan([c.model_dump() for c in body.changes], slugs, body.file_name,
                                        _user_label(user), body.model_dump(exclude={"changes", "file_name"}))
    except obl.ObligationError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    for slug in res.pop("slugs", []):
        sync_one(db, slug)
    return res


@router.get("/ui/bundle.js", name="ops_ui_bundle")
def ui_bundle(user: User = Depends(require_ops_user)):
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
    roles = effective_roles(db, user)
    if "admin" not in roles:
        # сотрудник — только экран «Компании» (без «Служебного» и блока в «Настройках»); остальным — ничего
        return [{"key": "ops", "title": "Компании", "path": "/x/ops", "bundle": "/api/ops/ui/bundle.js"}] \
            if "staff" in roles else []
    return [{
        "key": "ops", "title": "Компании", "path": "/x/ops", "bundle": "/api/ops/ui/bundle.js",
        # Бандл умеет рисовать блок для страницы «Настройки» (список admin модуля).
        "settings": True,
    }, {
        # Служебное: синхронизация карточек и импорт отчётов — тот же бандл, вид по basePath.
        "key": "ops-service", "title": "Служебное", "path": "/x/ops-service", "bundle": "/api/ops/ui/bundle.js",
    }]
