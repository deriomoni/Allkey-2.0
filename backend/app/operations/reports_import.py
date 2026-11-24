"""Импорт ручного файла статусов отчётности (xlsx) → ops_company_reports.

Формат: каждый лист — одна форма (имя листа = форма, напр. «300.00»); в шапке есть
колонка «Наименование компании», остальные колонки — периоды; в ячейке — статус.

Двухшаговый и stateless: `parse_workbook` + `match_rows` дают предпросмотр, файл на
сервере не сохраняется; подтверждённые строки клиент присылает обратно в `commit_rows`.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from typing import Iterable, List, Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.operations.models import OpsCompany, OpsCompanyReport

NAME_HEADER_RE = re.compile(r"наименование", re.I)
# Служебные колонки, которые не являются периодами.
SKIP_HEADER_RE = re.compile(
    r"^(№|n|#|п/п|№ ?п/п|бин|иин|бин/иин|ответствен.*|бухгалтер.*|примечани.*|комментари.*|режим|ндс)$", re.I
)
LEGAL_FORMS = ("тоо", "ип", "ао", "оо", "чу", "too", "llp", "ltd", "ип/ооо", "ооо", "филиал")
STATUSES = ("due", "submitted", "accepted", "rejected", "not_required")


def norm(s: Optional[str]) -> str:
    """Нормализация названия для сопоставления: регистр, кавычки, ОПФ, ё, пробелы."""
    if not s:
        return ""
    s = str(s).lower().replace("ё", "е")
    s = re.sub(r"[«»\"'`“”„‘’()\[\].,;:]", " ", s)
    s = re.sub(r"[-–—_/]", " ", s)
    words = [w for w in s.split() if w not in LEGAL_FORMS]
    return " ".join(words)


def cell_status(raw) -> Optional[str]:
    """Статус по содержимому ячейки; None — ячейка пустая, строку не пишем."""
    if raw is None:
        return None
    if isinstance(raw, (dt.date, dt.datetime)):
        return "submitted"
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in ("-", "—", "–", "н/т", "нт", "нет", "не требуется", "не сдается", "не сдаётся", "x", "х") or "не треб" in s:
        return "not_required"
    if "отклон" in s or "ошибк" in s:
        return "rejected"
    if "принят" in s:
        return "accepted"
    if s in ("+", "✓", "✔", "v", "да", "ok", "ок") or "сдан" in s or "сдано" in s or "отправ" in s:
        return "submitted"
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}([./]\d{2,4})?", s):
        return "submitted"
    return "due"


def _header_text(v) -> str:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.strftime("%m.%Y")
    return str(v).strip() if v is not None else ""


def parse_workbook(content: bytes) -> dict:
    """Разбор файла. Возвращает {sheets: [...], rows: [...], warnings: [...]}."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows_out: List[dict] = []
    warnings: List[str] = []
    sheets: List[dict] = []
    for ws in wb.worksheets:
        form = ws.title.strip()
        grid = list(ws.iter_rows(values_only=True))
        header_idx = name_col = None
        for i, row in enumerate(grid[:15]):
            for j, v in enumerate(row):
                if v is not None and NAME_HEADER_RE.search(str(v)):
                    header_idx, name_col = i, j
                    break
            if header_idx is not None:
                break
        if header_idx is None:
            warnings.append(f"Лист «{form}»: нет колонки «Наименование компании» — пропущен")
            continue
        header = grid[header_idx]
        periods = []
        for j, v in enumerate(header):
            text = _header_text(v)
            if j == name_col or not text or SKIP_HEADER_RE.match(text):
                continue
            periods.append((j, text))
        if not periods:
            warnings.append(f"Лист «{form}»: нет колонок периодов — пропущен")
            continue
        n = 0
        for r_i, row in enumerate(grid[header_idx + 1:], start=header_idx + 2):
            name = row[name_col] if name_col < len(row) else None
            if name is None or not str(name).strip():
                continue
            cells = []
            for j, period in periods:
                raw = row[j] if j < len(row) else None
                status = cell_status(raw)
                if status is None:
                    continue
                cells.append({"period": period, "raw": _header_text(raw), "status": status})
            rows_out.append({
                "row_id": f"{form}:{r_i}",
                "form": form,
                "row_number": r_i,
                "company_text": str(name).strip(),
                "cells": cells,
            })
            n += 1
        sheets.append({"form": form, "rows": n, "periods": [p for _, p in periods]})
    wb.close()
    return {"sheets": sheets, "rows": rows_out, "warnings": warnings}


def build_index(companies: Iterable[OpsCompany]) -> dict:
    """norm(название/алиас/папка) → {company_id: способ}."""
    idx: dict = {}
    for c in companies:
        keys = [(c.name, "name"), (c.drive_folder_name, "folder_name")] + [(a, "alias") for a in (c.aliases or [])]
        for text, how in keys:
            k = norm(text)
            if k:
                idx.setdefault(k, {}).setdefault(c.id, how)
    return idx


def match_rows(db: Session, rows: List[dict]) -> List[dict]:
    companies = db.query(OpsCompany).all()
    idx = build_index(companies)
    by_id = {c.id: c for c in companies}
    for row in rows:
        hits = idx.get(norm(row["company_text"]), {})
        if len(hits) == 1:
            cid, how = next(iter(hits.items()))
            row["match"] = {"company_id": cid, "name": by_id[cid].name, "by": how}
            row["candidates"] = []
        else:
            row["match"] = None
            row["candidates"] = [{"company_id": cid, "name": by_id[cid].name} for cid in hits]
    return rows


def commit_rows(db: Session, rows: List[dict]) -> dict:
    """rows: [{company_id, form, cells: [{period, raw, status}]}]. Upsert по (company, form, period)."""
    valid_ids = {cid for (cid,) in db.query(OpsCompany.id).all()}
    created = updated = skipped = 0
    for row in rows:
        cid = row.get("company_id")
        form = str(row.get("form") or "").strip()
        if cid not in valid_ids or not form:
            skipped += 1
            continue
        for cell in row.get("cells") or []:
            period = str(cell.get("period") or "").strip()
            status = cell.get("status")
            if not period or status not in STATUSES:
                skipped += 1
                continue
            obj = db.query(OpsCompanyReport).filter_by(company_id=cid, form=form, period=period).first()
            raw = (str(cell.get("raw")) if cell.get("raw") is not None else None)
            if obj is None:
                db.add(OpsCompanyReport(company_id=cid, form=form, period=period, status=status,
                                        raw_value=raw, source="import_xlsx"))
                created += 1
            else:
                obj.status, obj.raw_value, obj.source = status, raw, "import_xlsx"
                updated += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


# --- Перенос строк между базами (локальная → боевая): только добавление ---------------------

LOAD_STATUSES = STATUSES + ("clarify",)  # clarify — «уточнить» из плана (source=plan)
LOAD_SOURCES = ("import_xlsx", "plan", "knp_watch", "manual")


def load_rows(db: Session, rows: List[dict]) -> dict:
    """rows: [{slug, form, period, status, raw_value, source}]. Компания — по slug.
    Строка пишется, только если для (компания, форма, период) ещё ничего нет: существующее
    (история, отметки knp-watch, ручные) не перезаписывается. Повторный запуск ничего не меняет."""
    by_slug = {slug: cid for cid, slug in db.query(OpsCompany.id, OpsCompany.slug).all()}
    existing = {(r.company_id, r.form, r.period) for r in db.query(OpsCompanyReport).all()}
    res = {"created": 0, "skipped_existing": 0, "unknown_company": 0, "invalid": 0}
    for r in rows:
        cid = by_slug.get(str(r.get("slug") or ""))
        form, period = str(r.get("form") or "").strip(), str(r.get("period") or "").strip()
        status, source = r.get("status"), r.get("source")
        if cid is None:
            res["unknown_company"] += 1
            continue
        if not form or not period or status not in LOAD_STATUSES or source not in LOAD_SOURCES:
            res["invalid"] += 1
            continue
        if (cid, form, period) in existing:
            res["skipped_existing"] += 1
            continue
        raw = r.get("raw_value")
        db.add(OpsCompanyReport(company_id=cid, form=form, period=period, status=status,
                                raw_value=str(raw)[:500] if raw is not None else None, source=source))
        existing.add((cid, form, period))
        res["created"] += 1
    db.commit()
    return res
