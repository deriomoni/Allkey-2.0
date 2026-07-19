import re
import math
import datetime as dt
from io import BytesIO
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app.reconciliation.aoa import read_aoa

OFF_RATE_THRESHOLD = 0.5

Cell = Any


def _mathround(x: float) -> int:
    # JS Math.round: половина округляется в сторону +inf
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _round4(n: float) -> float:
    return _mathround(n * 10000) / 10000


def _round2(n: float) -> float:
    return _mathround(n * 100) / 100


def _fmt_date(d: int, m: int, y: int) -> str:
    return f"{d:02d}.{m:02d}.{y}"


def _parse_date(v: Cell) -> Optional[str]:
    if isinstance(v, (dt.datetime, dt.date)):  # pd.Timestamp наследует datetime
        return _fmt_date(v.day, v.month, v.year)
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{2,4})", v.strip())
        if m:
            y = m.group(3)
            y = f"20{y}" if len(y) == 2 else y
            return _fmt_date(int(m.group(1)), int(m.group(2)), int(y))
    return None


def _parse_num(v: Cell) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    if not isinstance(v, str):
        return None
    s = re.sub(r"[\s\u00a0\u202f]", "", v)
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    # отвергаем всё, что не чистое число (напр. текстовую дату "15.01.2026")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def _parse_nb_rates(aoa: List[List[Cell]]) -> Dict[str, float]:
    m: Dict[str, float] = {}
    for row in aoa:
        if not row:
            continue
        date = None
        for c in row:
            date = _parse_date(c)
            if date:
                break
        if not date:
            continue
        rate: Optional[float] = None
        for c in row:
            n = _parse_num(c)
            if n is not None and n > 50 and (rate is None or n > rate):
                rate = n
        if rate is not None:
            m[date] = rate
    return m


def _balance_cutoff(aoa: List[List[Cell]]) -> float:
    # Колонки «Общий оборот»/«Текущее сальдо» стоят правее сумм операции и
    # содержат бланк-курс сальдо — до них сканирование чисел нужно прекратить.
    for row in aoa:
        if not row:
            continue
        if not any(isinstance(c, str) and re.search(r"дебет", c, re.I) for c in row):
            continue
        cut = math.inf
        for i, c in enumerate(row):
            if isinstance(c, str) and re.search(r"оборот|сальдо", c, re.I) and i < cut:
                cut = i
        if cut != math.inf:
            return cut
    return math.inf


def _collect_nums(row: Optional[List[Cell]], cutoff: float) -> List[float]:
    out: List[float] = []
    if not row:
        return out
    up = len(row) if cutoff == math.inf else min(len(row), int(cutoff))
    for k in range(1, up):
        n = _parse_num(row[k])
        if n is not None and n > 0:
            out.append(n)
    return out


def _best_pair(main_nums: List[float], val_nums: List[float],
               nb_rate: Optional[float]) -> Optional[Dict[str, float]]:
    kzt_cand = sorted({_round2(n) for n in main_nums if n > 0})
    usd_cand = sorted({_round2(n) for n in val_nums if n > 0})
    best = None  # (usd, kzt, score)
    for kzt in kzt_cand:
        for usd in usd_cand:
            ratio = kzt / usd
            if ratio < 50 or ratio > 2000:
                continue
            if nb_rate is not None:
                if ratio < nb_rate * 0.6 or ratio > nb_rate * 1.4:
                    continue
                score = abs(ratio - nb_rate)
            else:
                if ratio < 200 or ratio > 800:
                    continue
                score = -kzt  # без курса НБ считаем реальной самую крупную сумму
            if best is None or score < best[2]:
                best = (usd, kzt, score)
    return {"usd": best[0], "kzt": best[1]} if best else None


def _parse_1c(aoa: List[List[Cell]], nb: Dict[str, float]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cutoff = _balance_cutoff(aoa)
    n = len(aoa)
    for i in range(n):
        row = aoa[i] or []
        date = None
        for c in row:
            date = _parse_date(c)
            if date:
                break
        if not date:
            continue

        main_nums = _collect_nums(row, cutoff)
        nxt = (aoa[i + 1] if i + 1 < n else []) or []
        next_has_date = any(_parse_date(c) for c in nxt)
        val_nums = [] if next_has_date else _collect_nums(nxt, cutoff)

        nb_rate = nb.get(date)
        pick = _best_pair(main_nums, val_nums, nb_rate)
        if not pick:
            continue

        usd, kzt = pick["usd"], pick["kzt"]
        rate1c = _round4(kzt / usd)
        diff = _round4(rate1c - nb_rate) if nb_rate is not None else None
        if nb_rate is None:
            status = "no_nb"
        elif abs(diff) > OFF_RATE_THRESHOLD:
            status = "off"
        else:
            status = "ok"

        desc = ""
        for c in row:
            if isinstance(c, str) and c.strip() and not _parse_date(c):
                desc = c.strip()
                break

        rows.append({
            "date": date, "description": desc, "usd": usd, "kzt": kzt,
            "rate1c": rate1c, "rate_nb": nb_rate, "diff": diff, "status": status,
        })
    return rows


class CaseCurrencyService:
    """Сверка курса USD: карточка счёта 1С ↔ курсы Нацбанка."""

    def __init__(self, card_content: bytes, nb_content: bytes):
        self.card_content = card_content
        self.nb_content = nb_content

    def reconcile(self) -> Dict[str, Any]:
        card = read_aoa(self.card_content)
        nb = _parse_nb_rates(read_aoa(self.nb_content))
        rows = _parse_1c(card, nb)
        off_rate = sum(1 for r in rows if r["status"] == "off")
        no_nb = sum(1 for r in rows if r["status"] == "no_nb")
        return {
            "rows": rows,
            "matched": len(rows) - no_nb,
            "off_rate": off_rate,
            "no_nb": no_nb,
            "total_usd": _round4(sum(r["usd"] for r in rows)),
            "total_kzt": _round4(sum(r["kzt"] for r in rows)),
            "threshold": OFF_RATE_THRESHOLD,
        }


def _status_label(s: str) -> str:
    return {"off": "Расхождение", "no_nb": "Нет курса НБ"}.get(s, "OK")


def export_currency(result: Dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Сверка курсов"

    header = ["Дата", "Документ", "Сумма USD", "Сумма KZT",
              "Курс 1С", "Курс НБ", "Отклонение", "Статус"]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")

    for r in result.get("rows", []):
        ws.append([
            r.get("date"), r.get("description"), r.get("usd"), r.get("kzt"),
            r.get("rate1c"), r.get("rate_nb"), r.get("diff"),
            _status_label(r.get("status", "")),
        ])

    ws.append([])
    ws.append([
        "ИТОГО", "", _round4(result.get("total_usd", 0)),
        _round4(result.get("total_kzt", 0)), "", "", "",
        f"Расхождений: {result.get('off_rate', 0)}",
    ])

    for col, width in zip("ABCDEFGH", [12, 34, 14, 16, 12, 12, 12, 16]):
        ws.column_dimensions[col].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
