"""Экспорт списка компаний в xlsx и импорт форм из того же файла (итерация 3, 24.11.2026).

Экспорт — текущий отфильтрованный список экрана «Компании» (клиент присылает id строк; сервер
отбирает их через visible_companies — скрытые у не-admin не попадут ни при каких id).

Импорт (только admin, «Служебное»), файл того же формата:
  * сопоставление по БИН; строки без совпадения — в отчёт, компании не создаются;
  * меняются только колонки форм: «да» — форма добавляется в tax.forms (source: import_xlsx, date),
    пустая ячейка ничего не меняет, «нет» — форма убирается из tax.forms. Форму с основанием
    подтверждённого обязательства (basis) импорт не убирает — в отчёт;
  * режим и НДС из файла не записываются: отличаются от карточки — строка в расхождения (спор решает КГД);
  * два шага: preview (ничего не пишет) → apply (клиент присылает список изменений, сервер
    пересчитывает по текущим карточкам). Изменения — одним коммитом в prod-decisions клона allkey-ops
    (как решения из панели) вместе со строкой журнала reports/forms-import-log.csv.
В лог — только счётчики (раздел 1.1 ТЗ).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
from typing import Dict, List, Optional

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.operations.obligations import (
    ObligationError, _card_path, _lock, _replace_block, _run_validator, check_branch, commit_and_push,
)
from app.operations.sync import repo_path

logger = logging.getLogger("app.operations")

KEY_FORMS = ["300.00", "200.00", "101.04", "220.00", "100.00", "910.00", "700.00"]
REGIME_LABEL = {"general": "ОУР", "simplified": "Упрощёнка", "retail": "Розничный"}
REGIME_CODE = {v.lower(): k for k, v in REGIME_LABEL.items()} | {
    "общеустановленный порядок": "general", "упрощенка": "simplified", "снр (упрощ.)": "simplified",
}
HEADER = ["Название", "БИН", "Режим", "НДС", "НДС с", "Формы", *KEY_FORMS, "Папка на Диске"]
YES = {"да", "yes", "+", "1", "✓", "✔", "x", "х"}
NO = {"нет", "no", "-", "0", "—"}
JOURNAL = "reports/forms-import-log.csv"
JOURNAL_COLS = ["date", "file", "admin", "companies_in_file", "companies_changed", "forms_added", "forms_removed",
                "unmatched", "discrepancies", "blocked"]


# --- поля карточки --------------------------------------------------------------------------

def card_forms(card: dict) -> List[str]:
    """Коды форм из tax.forms (уникальные, по порядку KEY_FORMS, затем остальные по алфавиту)."""
    out = []
    for f in ((card or {}).get("tax") or {}).get("forms") or []:
        code = str(f.get("form") if isinstance(f, dict) else f or "").strip()
        if code and code not in out:
            out.append(code)
    key = [f for f in KEY_FORMS if f in out]
    return key + sorted(f for f in out if f not in KEY_FORMS)


def merged_forms(card: dict, plan: Optional[set] = None) -> List[str]:
    """«Формы» экрана «Компании» и экспорта (владелец 24.11.2026): tax.forms карточки ∪ формы плана на текущий год
    (ops_company_reports, source=plan). Импорт форм по-прежнему сравнивает и пишет только tax.forms (card_forms)."""
    out = card_forms(card)
    for f in plan or ():
        if f and f not in out:
            out.append(f)
    key = [f for f in KEY_FORMS if f in out]
    return key + sorted(f for f in out if f not in KEY_FORMS)


def card_vat_date(card: dict) -> Optional[str]:
    return ((card or {}).get("kgd") or {}).get("vat_date") or None


def _fmt_date(v) -> str:
    try:
        return dt.date.fromisoformat(str(v)[:10]).strftime("%d.%m.%Y")
    except Exception:  # noqa: BLE001
        return str(v or "")


# --- экспорт -------------------------------------------------------------------------------

def export_xlsx(items: List[dict]) -> bytes:
    """items — элементы списка экрана (как отдаёт /api/ops/companies)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Компании"
    ws.append(HEADER)
    for c in items:
        forms = c.get("forms") or []
        vat = c.get("vat_payer")
        ws.append([
            c.get("name"), c.get("bin") or "", REGIME_LABEL.get(c.get("tax_regime") or "", "не установлен"),
            "да" if vat is True else "нет" if vat is False else "не установлен",
            _fmt_date(c.get("vat_date")) if vat and c.get("vat_date") else "",
            ", ".join(forms + (["план не рассчитан"] if c.get("plan_missing") else [])),
            *["да" if f in forms else "" for f in KEY_FORMS], c.get("drive_url") or "",
        ])
    head_font, fill = Font(bold=True), PatternFill("solid", fgColor="FFD9D9D9")
    for cell in ws[1]:
        cell.font, cell.fill = head_font, fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in ws["B"][1:]:
        cell.number_format = "@"
    for i, w in enumerate([42, 15, 13, 14, 12, 30, *[9] * len(KEY_FORMS), 50], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    for row in ws.iter_rows(min_row=2):
        link = row[-1]
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="FF0563C1", underline="single")
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- импорт: разбор файла ------------------------------------------------------------------

def _norm_head(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _norm_bin(v) -> str:
    s = re.sub(r"\D", "", str(v or "").split(".")[0])
    return s.zfill(12) if 0 < len(s) < 12 else s


def parse_xlsx(content: bytes) -> dict:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next((i for i, r in enumerate(rows[:10]) if any(_norm_head(v) == "бин" for v in r)), None)
    if hdr_i is None:
        raise ObligationError("В файле нет колонки «БИН» — нужен файл в формате экспорта «Компании»", 400)
    heads = [_norm_head(v) for v in rows[hdr_i]]
    col = {h: i for i, h in enumerate(heads) if h}
    form_cols = {f: col[f] for f in KEY_FORMS if f in col}
    if not form_cols:
        raise ObligationError("В файле нет колонок форм (300.00, 200.00, …)", 400)
    out, warnings = [], []
    for n, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        get = lambda h: r[col[h]] if h in col and col[h] < len(r) else None  # noqa: E731
        b = _norm_bin(get("бин"))
        name = str(get("название") or "").strip()
        if not b and not name:
            continue
        flags = {}
        for f, i in form_cols.items():
            v = str(r[i] if i < len(r) and r[i] is not None else "").strip().lower()
            if not v:
                continue
            if v in YES:
                flags[f] = "add"
            elif v in NO:
                flags[f] = "remove"
            else:
                warnings.append(f"строка {n}, {f}: «{r[i]}» — не «да»/«нет», пропущено")
        out.append({"row": n, "bin": b, "name": name, "regime": str(get("режим") or "").strip(),
                    "vat": str(get("ндс") or "").strip(), "flags": flags})
    return {"rows": out, "warnings": warnings, "form_columns": list(form_cols)}


# --- импорт: план изменений ----------------------------------------------------------------

def _regime_from_file(v: str) -> Optional[str]:
    s = v.strip().lower()
    if not s or s in ("—", "-", "не установлен"):
        return None
    return REGIME_CODE.get(s, "?" + s)


def _vat_from_file(v: str) -> Optional[bool]:
    s = v.strip().lower()
    return True if s == "да" else False if s == "нет" else None


def _blocked_removal(card: dict, form: str) -> bool:
    """Форма пришла из подтверждённого обязательства (есть basis) — импорт её не убирает."""
    for f in ((card.get("tax") or {}).get("forms") or []):
        if isinstance(f, dict) and str(f.get("form")) == form and f.get("basis"):
            return True
    return False


def build_plan(companies: list, parsed: dict) -> dict:
    """companies — OpsCompany (admin видит все). Ничего не пишет."""
    by_bin: Dict[str, list] = {}
    for c in companies:
        if c.bin:
            by_bin.setdefault(str(c.bin), []).append(c)
    changes, unmatched, disc, blocked = [], [], [], []
    seen = set()
    for r in parsed["rows"]:
        cands = by_bin.get(r["bin"]) or []
        if len(cands) != 1:
            unmatched.append({"row": r["row"], "bin": r["bin"], "name": r["name"],
                              "reason": "БИН не найден" if not cands else "БИН у нескольких карточек"})
            continue
        c = cands[0]
        if c.id in seen:
            unmatched.append({"row": r["row"], "bin": r["bin"], "name": r["name"], "reason": "повтор БИН в файле"})
            continue
        seen.add(c.id)
        card = c.card_json or {}
        tax = card.get("tax") or {}
        fr, cr = _regime_from_file(r["regime"]), tax.get("regime")
        if fr is not None and fr != cr:
            disc.append({"company": c.name, "bin": c.bin, "field": "режим", "file": r["regime"],
                         "card": REGIME_LABEL.get(cr or "", "не установлен")})
        fv, cv = _vat_from_file(r["vat"]), tax.get("vat_payer")
        if fv is not None and fv != cv:
            disc.append({"company": c.name, "bin": c.bin, "field": "НДС", "file": r["vat"],
                         "card": "да" if cv is True else "нет" if cv is False else "не установлен"})
        have = set(card_forms(card))
        add = [f for f, a in r["flags"].items() if a == "add" and f not in have]
        remove = []
        for f, a in r["flags"].items():
            if a == "remove" and f in have:
                if _blocked_removal(card, f):
                    blocked.append({"company": c.name, "bin": c.bin, "form": f,
                                    "reason": "форма по подтверждённому обязательству — снимается только в карточке"})
                else:
                    remove.append(f)
        if add or remove:
            changes.append({"company_id": c.id, "slug": c.slug, "name": c.name, "bin": c.bin,
                            "add": add, "remove": remove})
    return {
        "companies_in_file": len(parsed["rows"]),
        "matched": len(seen),
        "changes": changes,
        "unmatched": unmatched,
        "discrepancies": disc,
        "blocked": blocked,
        "warnings": parsed["warnings"],
        "totals": {"companies_changed": len(changes),
                   "forms_added": sum(len(x["add"]) for x in changes),
                   "forms_removed": sum(len(x["remove"]) for x in changes)},
    }


# --- импорт: применение --------------------------------------------------------------------

def _new_forms(card: dict, add: List[str], remove: List[str], today: str) -> list:
    forms = list(((card.get("tax") or {}).get("forms")) or [])
    rm = set(remove)
    forms = [f for f in forms if not (str(f.get("form") if isinstance(f, dict) else f) in rm
                                      and not (isinstance(f, dict) and f.get("basis")))]
    have = {str(f.get("form") if isinstance(f, dict) else f) for f in forms}
    for f in add:
        if f not in have:
            forms.append({"form": f, "source": "import_xlsx", "date": today})
    return forms


def apply_plan(changes: List[dict], slugs: Dict[int, str], file_name: str, user_label: str, summary: dict) -> dict:
    """changes: [{company_id, add, remove}] из предпросмотра; slugs — id → slug (только существующие)."""
    root = repo_path()
    today = dt.date.today().isoformat()
    file_name = re.sub(r"[\r\n,]", " ", (file_name or "без имени"))[:120]
    with _lock:
        check_branch(root)
        paths, rels, originals, done = [], [], [], []
        try:
            for ch in changes:
                slug = slugs.get(ch.get("company_id"))
                if not slug:
                    continue
                add = [f for f in ch.get("add") or [] if f in KEY_FORMS]
                remove = [f for f in ch.get("remove") or [] if f in KEY_FORMS]
                path = _card_path(root, slug)
                original = path.read_text(encoding="utf-8")
                card = yaml.safe_load(original) or {}
                before = card_forms(card)
                forms = _new_forms(card, add, remove, today)
                text = _replace_block(original, r"^  forms:", "forms:", forms, 4)
                check = yaml.safe_load(text) or {}
                b2, a2 = dict(card), dict(check)
                bt, at = dict(b2.get("tax") or {}), dict(a2.get("tax") or {})
                bt.pop("forms", None), at.pop("forms", None)
                b2["tax"], a2["tax"] = bt, at
                if b2 != a2:
                    raise ObligationError("Не удалось корректно записать карточку", 500)
                if card_forms(check) == before:
                    continue  # к этому моменту уже так
                path.write_text(text, encoding="utf-8", newline="\n")
                paths.append(path), rels.append(path.relative_to(root).as_posix()), originals.append(original)
                done.append({"slug": slug, "added": [f for f in card_forms(check) if f not in before],
                             "removed": [f for f in before if f not in card_forms(check)]})
            if not done:
                return {"ok": True, "commit": None, "companies_changed": 0, "forms_added": 0, "forms_removed": 0}
            for d in done:
                err = _run_validator(root, d["slug"])
                if err:
                    raise ObligationError("Валидатор карточек отклонил изменение: " + err, 422)
            # журнал импорта — в том же коммите
            jpath = root / JOURNAL
            jexists = jpath.is_file()
            jorig = jpath.read_text(encoding="utf-8") if jexists else None
            jpath.parent.mkdir(parents=True, exist_ok=True)
            with open(jpath, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=JOURNAL_COLS)
                if not jexists:
                    w.writeheader()
                w.writerow({
                    "date": dt.datetime.now().isoformat(timespec="seconds"), "file": file_name, "admin": user_label,
                    "companies_in_file": summary.get("companies_in_file", ""),
                    "companies_changed": len(done),
                    "forms_added": sum(len(d["added"]) for d in done),
                    "forms_removed": sum(len(d["removed"]) for d in done),
                    "unmatched": summary.get("unmatched", ""), "discrepancies": summary.get("discrepancies", ""),
                    "blocked": summary.get("blocked", ""),
                })
            paths.append(jpath), originals.append(jorig if jorig is not None else "")
            msg = (f"forms-import: {len(done)} карточ(ек), +{sum(len(d['added']) for d in done)} / "
                   f"-{sum(len(d['removed']) for d in done)} форм — файл «{file_name}» (admin {user_label})")
            sha = commit_and_push(root, paths, rels, originals, msg, new_files=[JOURNAL])
        except Exception:
            for p, o in zip(paths, originals):
                if p == root / JOURNAL and not o:
                    p.unlink(missing_ok=True)
                else:
                    p.write_text(o, encoding="utf-8", newline="\n")
            raise
    logger.info("ops: forms import committed %s (%d cards)", sha, len(done))
    return {"ok": True, "commit": sha, "companies_changed": len(done),
            "forms_added": sum(len(d["added"]) for d in done),
            "forms_removed": sum(len(d["removed"]) for d in done),
            "slugs": [d["slug"] for d in done]}
