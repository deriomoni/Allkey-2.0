import re
import math
import datetime as dt
from io import BytesIO
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app.reconciliation.aoa import read_aoa

OFF_RATE_THRESHOLD = 0.5
BALANCE_TOLERANCE = 0.01  # 1% — порог для контрольной проверки сальдо

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


def _date_key(d: str) -> int:
    dd, mm, yy = (int(x) for x in d.split("."))
    return yy * 10000 + mm * 100 + dd


def _parse_num(v: Cell) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    if not isinstance(v, str):
        return None
    s = re.sub(r"[\s  ]", "", v)
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


def _norm(c) -> str:
    return re.sub(r"\s+", " ", str(c)).strip().lower() if isinstance(c, str) else ""


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


def _account_cols(aoa: List[List[Cell]]) -> set:
    """Индексы колонок «Счёт» (номера счетов 1030/1710/…) — по подзаголовку под
    строкой с «Дебет»/«Кредит», как в case_bank_service. Их числа НЕ должны
    попадать в кандидаты сумм: иначе счёт 1030 в паре с ~2 EUR даёт отношение
    ~515 и проходит как правдоподобный курс. Пусто, если шапка не распознана —
    тогда поведение как раньше.
    """
    for i, row in enumerate(aoa):
        if not row:
            continue
        has_deb = any(isinstance(c, str) and c.strip().lower() == "дебет" for c in row)
        has_kre = any(isinstance(c, str) and c.strip().lower() == "кредит" for c in row)
        if not (has_deb and has_kre):
            continue
        sub = aoa[i + 1] if i + 1 < len(aoa) else []
        cols = {j for j, c in enumerate(sub) if _norm(c) in ("счет", "счёт")}
        if cols:
            return cols
    return set()


def _collect_nums(row: Optional[List[Cell]], cutoff: float, skip: set = frozenset()) -> List[float]:
    out: List[float] = []
    if not row:
        return out
    up = len(row) if cutoff == math.inf else min(len(row), int(cutoff))
    for k in range(1, up):
        if k in skip:
            continue
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
    acct = _account_cols(aoa)
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

        main_nums = _collect_nums(row, cutoff, acct)
        nxt = (aoa[i + 1] if i + 1 < n else []) or []
        next_has_date = any(_parse_date(c) for c in nxt)
        val_nums = [] if next_has_date else _collect_nums(nxt, cutoff, acct)

        nb_rate = nb.get(date)

        desc = ""
        for c in row:
            if isinstance(c, str) and c.strip() and not _parse_date(c):
                desc = c.strip()
                break

        base = {"date": date, "description": desc, "rate_nb": nb_rate,
                "expected_kzt": None, "delta_kzt": None}

        # Ни одна датированная строка не должна молча исчезать. Порядок статусов:
        # 1) нет валютной суммы вовсе — переоценка валютных средств (информационно);
        if not val_nums:
            rows.append({**base, "usd": None, "kzt": None, "rate1c": None,
                         "diff": None, "status": "no_val"})
            continue

        pick = _best_pair(main_nums, val_nums, nb_rate)

        # 2) есть тенге и валюта, но пара не прошла фильтр правдоподобия
        #    (отношение вне 50–2000). Так выглядит документ, проведённый без курса
        #    (тенге ≈ валюта, отношение ≈ 1). Это ошибка, а не инфо-строка.
        if pick is None:
            usd = max(val_nums)
            kzt = max(main_nums) if main_nums else None
            rate1c = _round4(kzt / usd) if (kzt is not None and usd) else None
            expected = _round2(usd * nb_rate) if nb_rate is not None else None
            delta = _round2(expected - kzt) if (expected is not None and kzt is not None) else None
            rows.append({**base, "usd": usd, "kzt": kzt, "rate1c": rate1c,
                         "diff": None, "expected_kzt": expected, "delta_kzt": delta,
                         "status": "no_rate"})
            continue

        # 3) пара найдена — обычная сверка с курсом НБ.
        usd, kzt = pick["usd"], pick["kzt"]
        rate1c = _round4(kzt / usd)
        diff = _round4(rate1c - nb_rate) if nb_rate is not None else None
        if nb_rate is None:
            status = "no_nb"
        elif abs(diff) > OFF_RATE_THRESHOLD:
            status = "off"
        else:
            status = "ok"
        rows.append({**base, "usd": usd, "kzt": kzt, "rate1c": rate1c,
                     "diff": diff, "status": status})
    return rows


def _last_date(aoa: List[List[Cell]]) -> Optional[str]:
    best_key = -1
    best: Optional[str] = None
    for row in aoa:
        for c in row or []:
            d = _parse_date(c)
            if d:
                k = _date_key(d)
                if k > best_key:
                    best_key, best = k, d
                break
    return best


def _last_num(row: Optional[List[Cell]]) -> Optional[float]:
    last: Optional[float] = None
    for c in row or []:
        n = _parse_num(c)
        if n is not None:
            last = n
    return last


def _balance_check(aoa: List[List[Cell]], nb: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """Контроль сальдо на конец: независимая проверка «в целом».

    В карточке в конце есть блок «Обороты за период и сальдо на конец»: строка
    «БУ» несёт сальдо в тенге (последнее число строки — «Текущее сальдо»), а
    следующая строка «Вал.» — сальдо в валюте. Подразумеваемый курс
    сальдо_KZT/сальдо_вал сверяется с курсом НБ на последнюю дату карточки.
    Возвращает None, если блок не найден (не падаем).
    """
    last_date = _last_date(aoa)
    for i, row in enumerate(aoa):
        label = row[0] if (row and isinstance(row[0], str)) else ""
        if not re.search(r"Сальдо на конец|Обороты за период", label, re.I):
            continue
        val_row = aoa[i + 1] if i + 1 < len(aoa) else []
        saldo_kzt = _last_num(row)
        saldo_val = _last_num(val_row)
        if saldo_val is None:
            return None

        rate_nb = nb.get(last_date) if last_date else None
        implied = (_round4(saldo_kzt / saldo_val)
                   if (saldo_kzt is not None and abs(saldo_val) > 1e-9) else None)
        expected = _round2(saldo_val * rate_nb) if rate_nb is not None else None
        diff = (_round2(saldo_kzt - expected)
                if (expected is not None and saldo_kzt is not None) else None)

        if abs(saldo_val) < 1e-9:
            # Валютное сальдо ноль, а тенговое нет — тоже расхождение.
            mismatch = bool(saldo_kzt is not None and abs(saldo_kzt) > 0.005)
        elif rate_nb is not None and implied is not None:
            mismatch = abs(implied / rate_nb - 1) > BALANCE_TOLERANCE
        else:
            mismatch = False

        return {
            "date": last_date,
            "saldo_val": saldo_val,
            "saldo_kzt": saldo_kzt,
            "rate_nb": rate_nb,
            "implied_rate": implied,
            "expected_kzt": expected,
            "diff": diff,
            "mismatch": mismatch,
        }
    return None


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
        no_rate = sum(1 for r in rows if r["status"] == "no_rate")
        no_val = sum(1 for r in rows if r["status"] == "no_val")
        matched = sum(1 for r in rows if r["status"] in ("ok", "off"))
        return {
            "rows": rows,
            "matched": matched,
            "off_rate": off_rate,
            "no_nb": no_nb,
            "no_rate": no_rate,
            "no_val": no_val,
            "total_rows": len(rows),
            "total_usd": _round4(sum(r["usd"] for r in rows if r.get("usd") is not None)),
            "total_kzt": _round4(sum(r["kzt"] for r in rows if r.get("kzt") is not None)),
            "threshold": OFF_RATE_THRESHOLD,
            "balance_check": _balance_check(card, nb),
        }


def _status_label(s: str) -> str:
    return {
        "off": "Расхождение",
        "no_nb": "Нет курса НБ",
        "no_rate": "Курс не определён",
        "no_val": "Нет валютной суммы",
    }.get(s, "OK")


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def _money(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


def _verdict_reasons(result: Dict[str, Any]) -> List[str]:
    """Список сработавших проверок обычным языком (пусто = всё чисто).

    Учитывает все проверки, а не только построчные счётчики: расхождение курса,
    неопределённый курс И контроль сальдо. Общий для страницы и Excel-отчёта.
    """
    reasons: List[str] = []
    off = result.get("off_rate", 0) or 0
    no_rate = result.get("no_rate", 0) or 0
    bc = result.get("balance_check")
    if off:
        reasons.append(f"Расхождение курса с Нацбанком: {off} {_plural(off, 'документ', 'документа', 'документов')}")
    if no_rate:
        reasons.append(f"Курс не определён: {no_rate} {_plural(no_rate, 'документ', 'документа', 'документов')}")
    if bc and bc.get("mismatch"):
        reasons.append(f"Контроль сальдо: расхождение {_money(abs(bc.get('diff') or 0))} ₸")
    return reasons


def _caveat(result: Dict[str, Any]) -> Optional[str]:
    """Жёлтая оговорка (не расхождение): строки, которые нельзя было проверить —
    нет курса НБ на их даты. Не краснит вердикт, но и не пропадает молча."""
    n = result.get("no_nb", 0) or 0
    if not n:
        return None
    return (f"{n} {_plural(n, 'строка', 'строки', 'строк')} "
            f"{_plural(n, 'не проверена', 'не проверены', 'не проверено')} — "
            "нет курса НБ на эти даты")


def export_currency(result: Dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Сверка курсов"

    # --- Общий вердикт первой строкой листа (виден до любой прокрутки) ---
    reasons = _verdict_reasons(result)
    if reasons:
        verdict = "НАЙДЕНЫ РАСХОЖДЕНИЯ: " + "; ".join(reasons)
        verdict_color = "CC0000"
    else:
        verdict = "Расхождений не найдено"
        verdict_color = "008000"
    ws.append([verdict])
    ws.cell(row=1, column=1).font = Font(bold=True, color=verdict_color)
    caveat = _caveat(result)
    if caveat:
        ws.append([caveat])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="B45309")
    ws.append([])

    header = ["Дата", "Документ", "Сумма USD", "Сумма KZT", "Курс 1С", "Курс НБ",
              "Отклонение", "Должно быть KZT", "Разница KZT", "Статус"]
    ws.append(header)
    # max_row корректен только после добавления строки с ячейками (пустая строка-
    # разделитель в max_row не учитывается), поэтому берём индекс шапки здесь.
    header_row = ws.max_row
    for c in ws[header_row]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")

    for r in result.get("rows", []):
        ws.append([
            r.get("date"), r.get("description"), r.get("usd"), r.get("kzt"),
            r.get("rate1c"), r.get("rate_nb"), r.get("diff"),
            r.get("expected_kzt"), r.get("delta_kzt"),
            _status_label(r.get("status", "")),
        ])

    rows = result.get("rows", [])
    ok = sum(1 for r in rows if r.get("status") == "ok")
    bc = result.get("balance_check")
    if bc is None:
        saldo_txt = ""
    else:
        saldo_txt = " · Контроль сальдо: " + ("РАСХОЖДЕНИЕ" if bc.get("mismatch") else "сходится")
    ws.append([])
    ws.append([
        "ИТОГО", "", _round4(result.get("total_usd", 0)),
        _round4(result.get("total_kzt", 0)), "", "", "", "", "",
        (f"Строк: {result.get('total_rows', len(rows))} · OK: {ok} · "
         f"Расхождений: {result.get('off_rate', 0)} · Нет курса НБ: {result.get('no_nb', 0)} · "
         f"Курс не определён: {result.get('no_rate', 0)} · Без валютной суммы: {result.get('no_val', 0)}"
         f"{saldo_txt}"),
    ])

    # --- Контроль сальдо ---
    bc = result.get("balance_check")
    if bc:
        ws.append([])
        ws.append([])
        title = ws.max_row + 1
        ws.append(["Контроль сальдо на конец периода"])
        ws.cell(row=title, column=1).font = Font(bold=True)
        ws.append(["Сальдо в валюте", bc.get("saldo_val")])
        ws.append(["Сальдо в тенге", bc.get("saldo_kzt")])
        ws.append(["Курс НБ на последнюю дату", bc.get("rate_nb")])
        ws.append(["Подразумеваемый курс (сальдо ₸ / сальдо вал.)", bc.get("implied_rate")])
        ws.append(["Ожидаемое сальдо в тенге (по курсу НБ)", bc.get("expected_kzt")])
        ws.append(["Разница", bc.get("diff")])
        ws.append(["Итог", "РАСХОЖДЕНИЕ" if bc.get("mismatch") else "Сходится"])

    for col, width in zip("ABCDEFGHIJ", [12, 34, 14, 16, 12, 12, 12, 18, 18, 20]):
        ws.column_dimensions[col].width = width

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
