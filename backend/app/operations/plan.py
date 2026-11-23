"""План отчётов из allkey-ops (`reports/plan-2026.csv`) → ops_company_reports с source='plan'.

* Загрузка аддитивная: строки истории (`import_xlsx`, `knp_watch`, `manual`) не трогаются.
  Если план совпал с историей по (компания, форма, период) — строка плана пропускается
  и попадает в счётчик `conflicts_with_history` (уникальный ключ таблицы общий).
* Повторная загрузка того же файла идемпотентна: строки плана обновляются, но принятое
  решение по «уточнить» (decision) не сбрасывается.
* Решение по «уточнить» пишется в строку и в ops_card_proposals (pending). Карточка
  (client.yaml) не меняется — применить предложение можно только отдельным шагом.
* Привязка к компании — по slug (устойчивый ключ), не по названию и не по порядку.

В лог — только счётчики (раздел 1.1 ТЗ).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from app.operations.config import get_ops_settings
from app.operations.models import OpsCardProposal, OpsCompany, OpsCompanyReport

logger = logging.getLogger("app.operations")

PLAN_FILE = "reports/plan-2026.csv"
DISCREPANCIES_GLOB = "discrepancies-*.csv"
PLAN_SOURCE = "plan"
PLAN_COLUMNS = (
    "company_slug", "bin", "form", "period", "due_date", "status", "clarify_reason",
    "basis", "info_source", "regime", "vat", "registry_sheet",
)
PLAN_STATUS = {"ожидается": "due", "уточнить": "clarify"}
STATUS_LABEL = {
    "due": "ожидается", "clarify": "уточнить", "not_required": "не требуется",
    "submitted": "сдано", "accepted": "принято", "rejected": "отклонено",
}
DECISIONS = {"confirmed": "due", "not_required": "not_required"}


class PlanError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def norm_period(raw: str) -> str:
    """«4 кв. 2026» → 2026-Q4, «2 п/г 2026» → 2026-H2, «2026» → 2026 (как у истории).
    Нестандартное («2026 / 2 п/г 2026», «по запросу») хранится как есть."""
    s = (raw or "").strip()
    m = re.fullmatch(r"([1-4])\s*кв\.?\s*(\d{4})", s, re.I)
    if m:
        return f"{m.group(2)}-Q{m.group(1)}"
    m = re.fullmatch(r"([12])\s*п/г\s*(\d{4})", s, re.I)
    if m:
        return f"{m.group(2)}-H{m.group(1)}"
    return s


def _repo() -> Path:
    p = (get_ops_settings().arty_ops_path or "").strip()
    if not p:
        raise PlanError("Не задан ARTY_OPS_PATH — путь к клону allkey-ops", 409)
    return Path(p)


def read_plan_csv(text: str) -> List[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in PLAN_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise PlanError("В файле плана нет колонок: " + ", ".join(missing))
    return [{k: (row.get(k) or "").strip() for k in PLAN_COLUMNS} for row in reader]


def load_plan(db: Session, rows: Iterable[dict], plan_file: str = PLAN_FILE) -> dict:
    by_slug: Dict[str, int] = {slug: cid for cid, slug in db.query(OpsCompany.id, OpsCompany.slug).all()}
    created = updated = conflicts = unknown = invalid = 0
    for r in rows:
        cid = by_slug.get(r["company_slug"])
        if cid is None:
            unknown += 1
            continue
        status = PLAN_STATUS.get(r["status"].lower())
        if not r["form"] or not r["period"] or status is None:
            invalid += 1
            continue
        period = norm_period(r["period"])
        plan_json = {
            "period_raw": r["period"], "plan_status": status, "clarify_reason": r["clarify_reason"] or None,
            "basis": r["basis"] or None, "info_source": r["info_source"] or None, "regime": r["regime"] or None,
            "vat": r["vat"] or None, "registry_sheet": r["registry_sheet"] or r["form"], "bin": r["bin"] or None,
            "plan_file": plan_file,
        }
        obj = db.query(OpsCompanyReport).filter_by(company_id=cid, form=r["form"], period=period).first()
        if obj is None:
            db.add(OpsCompanyReport(company_id=cid, form=r["form"], period=period, status=status,
                                    raw_value=r["status"], source=PLAN_SOURCE, due_date=r["due_date"] or None,
                                    plan_json=plan_json))
            created += 1
        elif obj.source != PLAN_SOURCE:
            conflicts += 1  # история важнее плана — не затираем
        else:
            obj.plan_json, obj.due_date, obj.raw_value = plan_json, r["due_date"] or None, r["status"]
            if not obj.decision:
                obj.status = status
            updated += 1
    db.commit()
    res = {"created": created, "updated": updated, "conflicts_with_history": conflicts,
           "unknown_company": unknown, "invalid": invalid}
    logger.info("ops plan load: %s", res)
    return res


def load_plan_from_repo(db: Session) -> dict:
    p = _repo() / PLAN_FILE
    if not p.is_file():
        raise PlanError(f"В клоне allkey-ops нет {PLAN_FILE} — обновите клон (git pull)", 404)
    return load_plan(db, read_plan_csv(p.read_text(encoding="utf-8")), PLAN_FILE)


def read_discrepancies() -> dict:
    d = _repo() / "reports"
    files = sorted(d.glob(DISCREPANCIES_GLOB)) if d.is_dir() else []
    if not files:
        return {"file": None, "items": []}
    f = files[-1]
    reader = csv.DictReader(io.StringIO(f.read_text(encoding="utf-8").lstrip("﻿")))
    items = [{k: (row.get(k) or "").strip() for k in ("company_slug", "company", "discrepancy", "source")}
             for row in reader]
    return {"file": f"reports/{f.name}", "items": items}


# --- Выдача строк плана -------------------------------------------------------------------

def plan_items(db: Session) -> List[dict]:
    q = (
        db.query(OpsCompanyReport, OpsCompany)
        .join(OpsCompany, OpsCompany.id == OpsCompanyReport.company_id)
        .filter(OpsCompanyReport.source == PLAN_SOURCE)
        .order_by(OpsCompany.name, OpsCompanyReport.form, OpsCompanyReport.period)
    )
    out = []
    for r, c in q.all():
        pj = r.plan_json or {}
        out.append({
            "id": r.id, "company_id": c.id, "company": c.name, "slug": c.slug,
            "bin": c.bin or pj.get("bin"), "regime": pj.get("regime"), "vat": pj.get("vat"),
            "form": r.form, "period": pj.get("period_raw") or r.period, "period_code": r.period,
            "due_date": r.due_date, "status": r.status, "plan_status": pj.get("plan_status"),
            "clarify_reason": pj.get("clarify_reason"), "basis": pj.get("basis"),
            "info_source": pj.get("info_source"), "registry_sheet": pj.get("registry_sheet") or r.form,
            "decision": r.decision, "decision_basis": r.decision_basis, "decided_by": r.decided_by,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        })
    return out


def counters(items: List[dict]) -> dict:
    companies = {i["company_id"] for i in items}
    with_due = {i["company_id"] for i in items if i["status"] == "due"}
    return {
        "total": len(items),
        "due": sum(1 for i in items if i["status"] == "due"),
        "clarify": sum(1 for i in items if i["status"] == "clarify"),
        "not_required": sum(1 for i in items if i["status"] == "not_required"),
        "companies": len(companies),
        "companies_without_forms": len(companies - with_due),
        "companies_without_forms_ids": sorted(companies - with_due),
    }


def apply_filters(items: List[dict], period: Optional[str] = None, form: Optional[str] = None,
                  status: Optional[str] = None, regime: Optional[str] = None,
                  without_forms: bool = False) -> List[dict]:
    if without_forms:
        ids = set(counters(items)["companies_without_forms_ids"])
        items = [i for i in items if i["company_id"] in ids]
    if period:
        items = [i for i in items if i["period"] == period]
    if form:
        items = [i for i in items if i["form"] == form]
    if status:
        items = [i for i in items if i["status"] == status]
    if regime:
        items = [i for i in items if (i["regime"] or "") == regime]
    return items


# --- Решение по «уточнить» ----------------------------------------------------------------

def _card_form_entry(card: dict, form: str):
    for f in ((card or {}).get("tax") or {}).get("forms") or []:
        if isinstance(f, dict) and str(f.get("form")) == form:
            return f
    return None


def decide(db: Session, report_id: int, decision: str, basis: str, user_label: str) -> dict:
    if decision not in DECISIONS:
        raise PlanError("Неизвестное решение")
    basis = (basis or "").strip()
    if len(basis) < 3:
        raise PlanError("Укажите основание решения")
    r = db.query(OpsCompanyReport).filter(OpsCompanyReport.id == report_id).first()
    if r is None or r.source != PLAN_SOURCE:
        raise PlanError("Not Found", 404)
    if r.status != "clarify" or r.decision:
        raise PlanError("По этой строке решение уже принято", 409)
    c = db.query(OpsCompany).filter(OpsCompany.id == r.company_id).first()
    now = dt.datetime.now(dt.timezone.utc)
    pj = r.plan_json or {}
    r.status = DECISIONS[decision]
    r.decision, r.decision_basis, r.decided_by, r.decided_at = decision, basis, user_label, now
    proposal = OpsCardProposal(
        company_id=r.company_id, proposed_by=user_label, field_path="tax.forms",
        old_value=_card_form_entry(c.card_json if c else {}, r.form),
        new_value={
            "action": "add_form" if decision == "confirmed" else "not_required",
            "form": r.form, "period": pj.get("period_raw") or r.period,
            "basis": basis, "source": "plan",
        },
        comment=f"Решение по строке плана «уточнить» ({pj.get('clarify_reason') or 'без причины'}): {basis}",
        status="pending", origin=f"report:{r.id}",
    )
    db.add(proposal)
    db.commit()
    logger.info("ops plan decision: %s", decision)
    return {"ok": True, "status": r.status, "proposal_id": proposal.id}


# --- Экспорт ------------------------------------------------------------------------------

_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")


def _sheet_title(name: str, used: set) -> str:
    base = (_SHEET_BAD.sub("_", name or "без листа").strip() or "без листа")[:31]
    title, n = base, 2
    while title.lower() in used:
        suffix = f" ({n})"
        title, n = base[: 31 - len(suffix)] + suffix, n + 1
    used.add(title.lower())
    return title


def _cell_text(i: dict) -> str:
    s = STATUS_LABEL.get(i["status"], i["status"])
    if i["status"] == "clarify" and i.get("clarify_reason"):
        s += f": {i['clarify_reason']}"
    if i.get("due_date") and i["status"] != "not_required":
        s += f" (срок {i['due_date']})"
    return s


def _bold_header(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"


def _xlsx(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_registry(items: List[dict]) -> bytes:
    """Формат реестра владельца: лист на форму (registry_sheet), строка — компания,
    колонки — периоды; в ячейке — статус (его понимает и импорт xlsx)."""
    wb = Workbook()
    wb.remove(wb.active)
    used: set = set()
    sheets: Dict[str, List[dict]] = {}
    for i in items:
        sheets.setdefault(i["registry_sheet"] or i["form"], []).append(i)
    for name in sorted(sheets):
        rows = sheets[name]
        ws = wb.create_sheet(_sheet_title(name, used))
        periods: List[str] = []
        for i in rows:
            if i["period"] not in periods:
                periods.append(i["period"])
        ws.append(["№", "Наименование компании", "БИН", "Режим", "НДС", "Форма", *periods])
        grouped: Dict[tuple, dict] = {}
        for i in rows:
            key = (i["company"], i["form"])
            g = grouped.setdefault(key, {"i": i, "cells": {}})
            g["cells"][i["period"]] = _cell_text(i)
        for n, ((company, form), g) in enumerate(sorted(grouped.items()), 1):
            i = g["i"]
            ws.append([n, company, i["bin"], i["regime"], i["vat"], form,
                       *[g["cells"].get(p, "") for p in periods]])
        _bold_header(ws)
        ws.column_dimensions["B"].width = 42
    if not wb.sheetnames:
        wb.create_sheet("пусто")
    return _xlsx(wb)


FLAT_HEADER = ["Компания", "БИН", "Режим", "НДС", "Форма", "Период", "Срок", "Статус", "Причина уточнения",
               "Основание", "Источник", "Лист реестра", "Решение", "Основание решения", "Кто решил", "Когда"]


def export_flat(items: List[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "План отчётов"
    ws.append(FLAT_HEADER)
    for i in items:
        ws.append([
            i["company"], i["bin"], i["regime"], i["vat"], i["form"], i["period"], i["due_date"],
            STATUS_LABEL.get(i["status"], i["status"]), i["clarify_reason"], i["basis"], i["info_source"],
            i["registry_sheet"], {"confirmed": "подтверждено: ожидается", "not_required": "не требуется"}.get(
                i["decision"] or "", ""), i["decision_basis"], i["decided_by"], i["decided_at"],
        ])
    _bold_header(ws)
    ws.column_dimensions["A"].width = 42
    ws.auto_filter.ref = ws.dimensions
    return _xlsx(wb)
