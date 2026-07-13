"""
Case 2: Reconciliation of two «Акт сверки взаиморасчётов» (1C statement of
mutual settlements) — the seller's copy and the buyer's copy of the same
balance.

Ported from the AI-BUH accountant logic (actReconcile reference), combined with
allkey's own safety nets (flexible number/date parsing, soft name matching and a
manual-mapping fallback).

Each act is a two-block sheet: the LEFT block «По данным <owner>» holds that
party's own books; the right block mirrors the other side. We compare each act's
OWN (left) block against the other's.

Matching (per the accountant):
  * goods — cross-reference number (seller's «Реализация №N» == buyer's
    «Накладная/Товарный чек № вх. N»); then by ЭСФ number (authoritative:
    «Электронный счет-фактура N» == «Счет-фактура полученный № вх. N»); then by
    date + amount for the rest (counter-supplies use each side's own numbering).
  * payments and returns — by date + amount.
Two acts often cover different periods, so items outside the common period are
reported separately («вне периода»), not as errors.

The public surface is unchanged: ``Case2Service(our_act_content,
counterparty_act_content, our_act_settings, counterparty_act_settings)`` and
``reconcile()`` (called by the /case2/process endpoint). The top-level response
keys are preserved; ``data`` rows and a few optional top-level keys are extended.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, date as _date
from typing import Any, Dict, List, Optional

import pandas as pd


# ------------------------------------------------------------------ operations
@dataclass
class ActOp:
    date: str            # DD.MM.YYYY
    date_key: int
    kind: str            # 'goods' | 'payment' | 'return' | 'other'
    num: str             # cross-reference document number
    doc_date: str        # accompanying document date (from «… от DD.MM.YYYY»)
    amount: Optional[float]
    debit: Optional[float]
    credit: Optional[float]
    esf_num: str
    has_ref: bool
    doc: str
    row: int             # 1-based source row


@dataclass
class ParsedAct:
    owner: str = ""
    owner_counterparty: str = ""
    start: int = 0
    end: int = 0
    period_text: str = ""
    opening: Optional[float] = None
    closing: Optional[float] = None
    turnover_d: Optional[float] = None
    turnover_k: Optional[float] = None
    ops: List[ActOp] = field(default_factory=list)
    auto: bool = True
    header_row: int = -1


# --------------------------------------------------------------- status labels
_STATUS_LABEL = {
    "ok": "Совпадает",
    "amount_mismatch": "Расхождение",
    "num_mismatch": "Расхождение",
    "date_mismatch": "Расхождение",
    "only_1": "Нет у контрагента",
    "only_2": "Нет у нас",
    "out_1": "Вне периода",
    "out_2": "Вне периода",
}
_STATUS_DETAIL = {
    "ok": "Совпадает",
    "amount_mismatch": "Расхождение суммы",
    "num_mismatch": "Номер не совпадает",
    "date_mismatch": "Разная дата",
    "only_1": "Нет во 2-м акте",
    "only_2": "Нет в 1-м акте",
    "out_1": "Вне периода (акт 1)",
    "out_2": "Вне периода (акт 2)",
}
_CAT_KIND = {"goods": "Реализация", "payment": "Оплата", "return": "Возврат", "other": "Прочее"}

_LEGAL_RE = re.compile(
    r'\b(тоо|ооо|ип|ао|зао|оао|товарищество с ограниченной ответственностью|филиал)\b', re.I
)

# Document types that START a new operation (used to reconstruct operations whose
# document text 1C split across several rows). Sub-lines like «Накладная/Товарный
# чек …» and «Счет-фактура …» are deliberately NOT here — they belong to the
# operation above them.
_OP_TYPE_RE = re.compile(
    r'^\s*(?:Поступлени|Реализац|Возврат|Платежное|Оплата|Списани|Корректировк|Авансов|Приходн|Расходн)',
    re.I,
)


class Case2Service:
    # Legacy defaults, used only when auto-detection fails and settings omit mappings.
    DEFAULT_DATE_COL = 1
    DEFAULT_DOCUMENT_COL = 2
    DEFAULT_DEBIT_COL = 4
    DEFAULT_CREDIT_COL = 5

    def __init__(
        self,
        our_act_content: bytes,
        counterparty_act_content: bytes,
        our_act_settings: Dict[str, Any],
        counterparty_act_settings: Dict[str, Any],
    ):
        self.our_act_content = our_act_content
        self.counterparty_act_content = counterparty_act_content
        self.our_act_settings = our_act_settings or {}
        self.counterparty_act_settings = counterparty_act_settings or {}

    # --------------------------------------------------------------- reading
    @staticmethod
    def _read_df(content: bytes) -> pd.DataFrame:
        """Read the first sheet as a raw (header=None) DataFrame.

        Handles .xls (xlrd) and .xlsx (openpyxl). Some 1C/counterparty exports
        name the OOXML parts with the wrong case (``xl/SharedStrings.xml``),
        which breaks openpyxl on case-sensitive filesystems (i.e. the Linux
        server); rebuild the archive with canonical lowercase names and retry.
        """
        if len(content) < 4:
            raise ValueError("Файл слишком маленький или пустой")
        if content[:2] == b"PK":  # xlsx (zip)
            try:
                return pd.read_excel(io.BytesIO(content), header=None, engine="openpyxl")
            except Exception:
                fixed = Case2Service._canonicalize_xlsx(content)
                return pd.read_excel(io.BytesIO(fixed), header=None, engine="openpyxl")
        if content[:2] == b"\xd0\xcf":  # xls (OLE2)
            return pd.read_excel(io.BytesIO(content), header=None, engine="xlrd")
        # Last resort: let pandas guess.
        return pd.read_excel(io.BytesIO(content), header=None)

    @staticmethod
    def _canonicalize_xlsx(content: bytes) -> bytes:
        canon = {
            "xl/sharedstrings.xml": "xl/sharedStrings.xml",
            "xl/styles.xml": "xl/styles.xml",
            "xl/workbook.xml": "xl/workbook.xml",
        }
        src = io.BytesIO(content)
        out = io.BytesIO()
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                zout.writestr(canon.get(name.lower(), name), zin.read(name))
        return out.getvalue()

    # --------------------------------------------------------------- parsers
    def _parse_number(self, value: Any) -> Optional[float]:
        """Flexible number parser: 8520, 8 520, 8 520,00, 8,520.00, NBSP-spaced."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, (int, float)):
            return float(value) if pd.notna(value) else None
        s = str(value).strip()
        if not s:
            return None
        s = s.replace(" ", "").replace(" ", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, value: Any) -> Optional[str]:
        """Flexible date parser → normalized DD.MM.YYYY."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, (pd.Timestamp, datetime, _date)):
            return value.strftime("%d.%m.%Y")
        s = str(value).strip()
        m = re.match(r"^(\d{1,2})[.](\d{1,2})[.](\d{2,4})", s)
        if m:
            y = m.group(3)
            if len(y) == 2:
                y = "20" + y
            return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{y}"
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
        return None

    @staticmethod
    def _date_key(d: str) -> int:
        dd, mm, yy = (int(x) for x in d.split("."))
        return yy * 10000 + mm * 100 + dd

    @staticmethod
    def _key_to_str(k: int) -> str:
        y, m, d = k // 10000, (k % 10000) // 100, k % 100
        return f"{d:02d}.{m:02d}.{y}"

    # --------------------------------------------------------- name matching
    @staticmethod
    def _normalize_name(name: str) -> str:
        s = (name or "").lower()
        s = _LEGAL_RE.sub(" ", s)
        s = re.sub(r"[\"«»'`,\.]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def _similar_names(self, a: str, b: str) -> bool:
        na, nb = self._normalize_name(a), self._normalize_name(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        wa, wb = set(na.split()), set(nb.split())
        if not wa or not wb:
            return False
        inter = wa & wb
        return bool(inter) and len(inter) / min(len(wa), len(wb)) >= 0.5

    # -------------------------------------------------------------- classify
    @staticmethod
    def _classify(doc: str) -> Dict[str, Any]:
        d = doc
        m = re.search(r"Реализац\w* ТМЗ и услуг\s+(\w+)(?:\s+от\s+(\d{2}\.\d{2}\.\d{4}))?", d, re.I)
        if m:
            return dict(kind="goods", num=m.group(1), doc_date=m.group(2) or "", has_ref=True)
        m = re.search(r"Поступлени\w* ТМЗ и услуг.*?№\s*вх\.\s*0*(\w+)(?:\s+от\s+(\d{2}\.\d{2}\.\d{4}))?", d, re.I)
        if m:
            return dict(kind="goods", num=m.group(1), doc_date=m.group(2) or "", has_ref=True)
        m = re.search(r"Накладная/Товарный чек\s*№\s*вх\.\s*0*(\w+)(?:\s+от\s+(\d{2}\.\d{2}\.\d{4}))?", d, re.I)
        if m:
            return dict(kind="goods", num=m.group(1), doc_date=m.group(2) or "", has_ref=True)
        # Counter-supply / plain receipt without «№ вх.» — own numbering; match by date+amount.
        m = re.search(r"Поступлени\w* ТМЗ и услуг\s+(\w+)\s+от\s+(\d{2}\.\d{2}\.\d{4})?", d, re.I)
        if m:
            return dict(kind="goods", num=m.group(1), doc_date=m.group(2) or "", has_ref=False)
        m = re.search(r"Возврат\D*?(\w*\d\w*)", d, re.I)
        if m:
            return dict(kind="return", num=m.group(1), doc_date="", has_ref=False)
        if re.search(r"Платежное поручение|Оплата|Списание с расчетного счета|Поступление на расчетный счет", d, re.I):
            p = (re.search(r"№\s*вх\.\s*0*(\d+)", d, re.I)
                 or re.search(r"\((?:входящее|исходящее)\)\s*(\w+)", d, re.I)
                 or re.search(r"(\d{3,})", d))
            return dict(kind="payment", num=(p.group(1) if p else ""), doc_date="", has_ref=False)
        return dict(kind="other", num="", doc_date="", has_ref=False)

    @staticmethod
    def _esf_number(doc: str) -> str:
        m = (re.search(r"Электронн\w* счет-фактура\s+№?\s*(?:вх\.?\s*)?0*(\w+)", doc, re.I)
             or re.search(r"Счет-фактура\s+(?:полученный|выданный)?\s*№?\s*(?:вх\.?\s*)?0*(\w+)", doc, re.I))
        if m:
            num = m.group(1)
            return "" if set(num) <= set("_") else num
        return ""

    # ------------------------------------------------------------ header find
    @staticmethod
    def _cell(df: pd.DataFrame, i: int, j: int) -> Any:
        if 0 <= i < df.shape[0] and 0 <= j < df.shape[1]:
            return df.iat[i, j]
        return None

    def _find_header(self, df: pd.DataFrame):
        """First row carrying «Дата» + «Документ» + «Дебет» + «Кредит».

        Returns (header_row, date_col, doc_col, debit_col, credit_col) using the
        LEFT-most occurrence of each label, or (-1, ...) if not found.
        """
        for i in range(min(len(df), 60)):
            idx = {"date": -1, "doc": -1, "deb": -1, "kre": -1}
            for j in range(df.shape[1]):
                v = self._cell(df, i, j)
                if not isinstance(v, str):
                    continue
                s = v.strip().lower()
                if idx["date"] < 0 and s == "дата":
                    idx["date"] = j
                elif idx["doc"] < 0 and s == "документ":
                    idx["doc"] = j
                elif idx["deb"] < 0 and s == "дебет":
                    idx["deb"] = j
                elif idx["kre"] < 0 and s == "кредит":
                    idx["kre"] = j
            if all(v >= 0 for v in idx.values()):
                return i, idx["date"], idx["doc"], idx["deb"], idx["kre"]
        return -1, self.DEFAULT_DATE_COL, self.DEFAULT_DOCUMENT_COL, self.DEFAULT_DEBIT_COL, self.DEFAULT_CREDIT_COL

    def _parse_act(self, content: bytes, settings: Dict[str, Any]) -> ParsedAct:
        df = self._read_df(content)
        hrow, date_col, doc_col, deb_col, kre_col = self._find_header(df)
        auto = hrow >= 0
        if not auto:
            # Manual fallback (allkey legacy): use settings header_row/column_mappings.
            cm = settings.get("column_mappings", {}) or {}
            date_col = cm.get("date", self.DEFAULT_DATE_COL)
            doc_col = cm.get("document", self.DEFAULT_DOCUMENT_COL)
            deb_col = cm.get("debit", self.DEFAULT_DEBIT_COL)
            kre_col = cm.get("credit", self.DEFAULT_CREDIT_COL)
            hrow = int(settings.get("header_row", 0)) - 1

        pa = ParsedAct(auto=auto, header_row=hrow)

        # owners: first «По данным … , KZT» (leftmost = own), second = counterparty
        owners = []
        for i in range(min(len(df), 40)):
            for j in range(df.shape[1]):
                v = self._cell(df, i, j)
                if isinstance(v, str) and re.search(r"По данным.*?KZT", v, re.I | re.S):
                    m = re.search(r"По данным\s+(.+?),\s*KZT", v, re.I | re.S)
                    owners.append((j, re.sub(r"\s+", " ", (m.group(1) if m else v)).strip()))
            if len(owners) >= 2:
                break
        owners.sort(key=lambda x: x[0])
        if owners:
            pa.owner = owners[0][1]
        if len(owners) > 1:
            pa.owner_counterparty = owners[1][1]

        # period «за период с DD.MM.YYYY по DD.MM.YYYY»
        for i in range(min(len(df), 40)):
            done = False
            for j in range(df.shape[1]):
                v = self._cell(df, i, j)
                if isinstance(v, str):
                    m = re.search(r"за период с\s*(\d{2}\.\d{2}\.\d{4})\s*по\s*(\d{2}\.\d{2}\.\d{4})", v, re.I)
                    if m:
                        pa.start = self._date_key(m.group(1))
                        pa.end = self._date_key(m.group(2))
                        pa.period_text = f"{m.group(1)}–{m.group(2)}"
                        done = True
                        break
            if done:
                break

        # header figures + operations
        #
        # 1C exports vary: some put a whole operation's document in one cell,
        # others split ONE operation across several rows — the type line
        # («Поступление ТМЗ и услуг») on one row, «NUMBER от DATE, Накладная …»
        # on the dated row that also carries the amount, then «вх. N»,
        # «Счет-фактура полученный», «№ вх. ЭСФ» and a separate ЭСФ-date row
        # below. We treat a dated row that carries an amount as the operation
        # "anchor" and reconstruct its full document from the surrounding block.
        def s(v):
            return v if isinstance(v, str) else ""

        i = hrow + 1
        n = len(df)
        while i < n:
            label = s(self._cell(df, i, date_col))
            if re.search(r"Сальдо на начало", label, re.I):
                pa.opening = self._parse_number(self._cell(df, i, deb_col))
                if pa.opening is None:
                    pa.opening = self._parse_number(self._cell(df, i, kre_col))
                i += 1
                continue
            if re.search(r"Обороты за период", label, re.I):
                pa.turnover_d = self._parse_number(self._cell(df, i, deb_col))
                pa.turnover_k = self._parse_number(self._cell(df, i, kre_col))
                i += 1
                continue
            if re.search(r"Сальдо на конец", label, re.I):
                pa.closing = self._parse_number(self._cell(df, i, deb_col))
                if pa.closing is None:
                    pa.closing = self._parse_number(self._cell(df, i, kre_col))
                i += 1
                continue

            parsed_date = self._parse_date(self._cell(df, i, date_col))
            doc_i = s(self._cell(df, i, doc_col))
            debit = self._parse_number(self._cell(df, i, deb_col))
            credit = self._parse_number(self._cell(df, i, kre_col))
            amount = debit if (debit is not None and debit != 0) else credit

            if parsed_date and amount is not None and amount != 0:
                # Anchor row → one real operation.
                parts = []
                # Prepend a type-only line sitting directly above (split layout).
                if not _OP_TYPE_RE.match(doc_i):
                    prev_doc = s(self._cell(df, i - 1, doc_col))
                    prev_date = self._parse_date(self._cell(df, i - 1, date_col))
                    if prev_doc and not prev_date and _OP_TYPE_RE.match(prev_doc):
                        parts.append(prev_doc)
                parts.append(doc_i)
                # Append following sub-rows (no own date) until the next operation.
                j = i + 1
                while j < n:
                    if self._parse_date(self._cell(df, j, date_col)):
                        break
                    sub = s(self._cell(df, j, doc_col))
                    if _OP_TYPE_RE.match(sub):
                        break  # start of the next operation
                    parts.append(sub)
                    j += 1
                full_doc = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
                c = self._classify(full_doc)
                pa.ops.append(ActOp(
                    date=parsed_date, date_key=self._date_key(parsed_date),
                    kind=c["kind"], num=c["num"], doc_date=c["doc_date"],
                    amount=amount, debit=debit, credit=credit,
                    esf_num=self._esf_number(full_doc), has_ref=c["has_ref"],
                    doc=full_doc, row=i + 1,
                ))
                i = j
                continue

            if parsed_date:
                # Dated row without an amount (ЭСФ date / spacer) — not an operation.
                i += 1
                continue

            # Undated continuation (single-cell layout) — attach ЭСФ to last op.
            if doc_i and pa.ops and not pa.ops[-1].esf_num:
                esf = self._esf_number(doc_i)
                if esf:
                    pa.ops[-1].esf_num = esf
            i += 1

        return pa

    # ------------------------------------------------------------- reconcile
    @staticmethod
    def _eq(a: Optional[float], b: Optional[float]) -> bool:
        return a is not None and b is not None and abs(a - b) < 0.005

    def reconcile(self) -> Dict[str, Any]:
        A = self._parse_act(self.our_act_content, self.our_act_settings)
        B = self._parse_act(self.counterparty_act_content, self.counterparty_act_settings)

        if not A.ops and not B.ops:
            return self._empty_result(A, B)

        common_start = max(A.start or 0, B.start or 0)
        if A.end and B.end:
            common_end = min(A.end, B.end)
        else:
            common_end = A.end or B.end or 10 ** 9

        def in_common(op: ActOp) -> bool:
            return common_start <= op.date_key <= common_end

        rows: List[Dict[str, Any]] = []
        out_rows: List[Dict[str, Any]] = []

        def push(row: Dict[str, Any], common: bool):
            (rows if common else out_rows).append(row)

        # ------------------------------------------------------ goods
        goods_a = [o for o in A.ops if o.kind == "goods"]
        goods_b = [o for o in B.ops if o.kind == "goods"]
        used_b: set = set()
        match_of: Dict[int, ActOp] = {}
        method_of: Dict[int, str] = {}

        # Pass 1 — cross-reference number.
        b_by_ref: Dict[str, List[ActOp]] = {}
        for o in goods_b:
            if o.has_ref and o.num:
                b_by_ref.setdefault(o.num, []).append(o)
        for s in goods_a:
            if not (s.has_ref and s.num):
                continue
            cands = [o for o in b_by_ref.get(s.num, []) if o.row not in used_b]
            if not cands:
                continue
            m = (next((o for o in cands if o.date == s.date and self._eq(o.amount, s.amount)), None)
                 or next((o for o in cands if self._eq(o.amount, s.amount)), None)
                 or cands[0])
            used_b.add(m.row); match_of[s.row] = m; method_of[s.row] = "Номер"

        # Pass 1b — by ЭСФ number (authoritative invoice identity).
        b_by_esf: Dict[str, List[ActOp]] = {}
        for o in goods_b:
            if o.esf_num and o.row not in used_b:
                b_by_esf.setdefault(o.esf_num, []).append(o)
        for s in goods_a:
            if s.row in match_of or not s.esf_num:
                continue
            cands = [o for o in b_by_esf.get(s.esf_num, []) if o.row not in used_b]
            if not cands:
                continue
            m = (next((o for o in cands if o.date == s.date and self._eq(o.amount, s.amount)), None)
                 or next((o for o in cands if self._eq(o.amount, s.amount)), None)
                 or cands[0])
            used_b.add(m.row); match_of[s.row] = m; method_of[s.row] = "ЭСФ"

        # Pass 2 — by date + amount for the rest.
        for s in goods_a:
            if s.row in match_of:
                continue
            alt = next((x for x in goods_b if x.row not in used_b and x.date == s.date and self._eq(x.amount, s.amount)), None)
            if alt:
                used_b.add(alt.row); match_of[s.row] = alt; method_of[s.row] = "Дата+сумма"

        for s in goods_a:
            m = match_of.get(s.row)
            method = method_of.get(s.row, "")
            status_code, note = "ok", ""
            counter = bool(m) and (not s.has_ref or not m.has_ref)
            if m:
                if not self._eq(s.amount, m.amount):
                    # The only real goods discrepancy: amounts disagree.
                    status_code = "amount_mismatch"
                    note = f"{self._fmt(s.amount)} / {self._fmt(m.amount)}"
                else:
                    # Amounts agree → operation reconciled. Document- and ЭСФ-number
                    # differences are informational: each side registers invoices in
                    # its own numbering (seller's realization № / ЭСФ № vs buyer's
                    # incoming «№ вх.»), so they legitimately differ. Not a расхождение.
                    same_num = bool(s.num and m.num and s.num == m.num)
                    same_esf = bool(s.esf_num and m.esf_num and s.esf_num == m.esf_num)
                    if same_num or same_esf:
                        bits = []
                        if s.num and m.num and s.num != m.num:
                            bits.append(f"номера: {s.num} / {m.num}")
                        if s.esf_num and m.esf_num and s.esf_num != m.esf_num:
                            bits.append(f"ЭСФ: {s.esf_num} / {m.esf_num}")
                        note = "; ".join(bits)
                    elif counter:
                        note = "встречная поставка (сверено по дате+сумме)"
                    else:
                        note = "сверено по дате+сумме"
            else:
                status_code = "only_1" if in_common(s) else "out_1"
            category = "Встречная" if counter else "Реализация"
            push(self._row(category, s, m, status_code, note, method), status_code != "out_1" and in_common(s))

        for m in goods_b:
            if m.row in used_b:
                continue
            status_code = "only_2" if in_common(m) else "out_2"
            push(self._row("Реализация", None, m, status_code, "", ""), in_common(m))

        # -------------------------------------------- payments & returns
        def match_da(cat_kind: str):
            list_b = [o for o in B.ops if o.kind == cat_kind]
            used: set = set()
            for s in [o for o in A.ops if o.kind == cat_kind]:
                m = next((x for x in list_b if x.row not in used and x.date == s.date and self._eq(x.amount, s.amount)), None)
                status_code, note = "ok", ""
                if not m:
                    alt = next((x for x in list_b if x.row not in used and self._eq(x.amount, s.amount)), None)
                    if alt:
                        m = alt; status_code = "date_mismatch"; note = f"{s.date} / {alt.date}"
                    else:
                        status_code = "only_1" if in_common(s) else "out_1"
                if m:
                    used.add(m.row)
                push(self._row(_CAT_KIND[cat_kind], s, m, status_code, note, "Дата+сумма" if m else ""),
                     status_code != "out_1" and in_common(s))
            for m in list_b:
                if m.row in used:
                    continue
                status_code = "only_2" if in_common(m) else "out_2"
                push(self._row(_CAT_KIND[cat_kind], None, m, status_code, "", ""), in_common(m))

        match_da("payment")
        match_da("return")

        rows.sort(key=lambda r: self._date_key(r["date"]))
        out_rows.sort(key=lambda r: self._date_key(r["date"]))

        matched = sum(1 for r in rows if r["status_code"] == "ok")
        mismatched = sum(1 for r in rows if r["status_code"] in ("amount_mismatch", "num_mismatch", "date_mismatch"))
        only1 = sum(1 for r in rows if r["status_code"] == "only_1")
        only2 = sum(1 for r in rows if r["status_code"] == "only_2")

        open_diff = None
        if A.opening is not None and B.opening is not None:
            open_diff = round(abs(A.opening) - abs(B.opening), 2)
        close_diff = None
        if A.closing is not None and B.closing is not None:
            close_diff = round(abs(A.closing) - abs(B.closing), 2)

        common_period = ""
        if common_start and common_end < 10 ** 9 and common_start <= common_end:
            common_period = f"{self._key_to_str(common_start)}–{self._key_to_str(common_end)}"
        period_mismatch = bool(A.period_text and B.period_text and A.period_text != B.period_text)

        names_similar = self._similar_names(A.owner, B.owner_counterparty) or \
            self._similar_names(B.owner, A.owner_counterparty)

        header_summary = {
            "owner_act1": A.owner,
            "owner_act2": B.owner,
            "period_act1": A.period_text,
            "period_act2": B.period_text,
            "period_mismatch": period_mismatch,
            "common_period": common_period,
            "names_consistent": names_similar,
            "opening_act1": A.opening, "opening_act2": B.opening, "opening_diff": open_diff,
            "closing_act1": A.closing, "closing_act2": B.closing, "closing_diff": close_diff,
            "turnover_debit_act1": A.turnover_d, "turnover_credit_act1": A.turnover_k,
            "turnover_debit_act2": B.turnover_d, "turnover_credit_act2": B.turnover_k,
        }

        total_records = len(rows)
        denom = matched + mismatched + only1 + only2
        match_rate = round(matched / denom * 100, 1) if denom else 100.0

        return {
            "status": "completed",
            "total_records": total_records,
            "matched": matched,
            "mismatched": mismatched,
            "not_found_in_source1": only1,
            "not_found_in_source2": only2,
            "data": rows,
            "out_of_period": out_rows,
            "header_summary": header_summary,
            "common_period": common_period,
            "period_mismatch": period_mismatch,
            "summary": {
                "total_entries_act1": len(A.ops),
                "total_entries_act2": len(B.ops),
                "matched_count": matched,
                "match_rate": match_rate,
                "has_discrepancies": mismatched > 0 or only1 > 0 or only2 > 0,
                "auto_detected": A.auto and B.auto,
            },
        }

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _fmt(n: Optional[float]) -> str:
        return "—" if n is None else f"{n}"

    def _row(self, category: str, a: Optional[ActOp], b: Optional[ActOp],
             status_code: str, note: str, method: str) -> Dict[str, Any]:
        """Build a result row: act-reconcile fields + allkey back-compat keys."""
        a_amt = a.amount if a else None
        b_amt = b.amount if b else None
        return {
            # act-reconcile domain
            "category": category,
            "date": (a.date if a else (b.date if b else "")),
            "num1": (a.num if a else ""),
            "num2": (b.num if b else ""),
            "amount1": a_amt,
            "amount2": b_amt,
            "esf1": (a.esf_num if a else ""),
            "esf2": (b.esf_num if b else ""),
            "note": note,
            "match_method": method,
            "status_code": status_code,
            "status_detail": _STATUS_DETAIL[status_code],
            "row1": (a.row if a else ""),
            "row2": (b.row if b else ""),
            # allkey back-compat keys (frontend/excel already read these)
            "document": (a.doc if a else (b.doc if b else "")),
            "cp_document": (b.doc if b else ""),
            "our_doc_number": (a.num if a else None),
            "cp_doc_number": (b.num if b else None),
            "our_debit": (a.debit if a else None),
            "our_credit": (a.credit if a else None),
            "cp_debit": (b.debit if b else None),
            "cp_credit": (b.credit if b else None),
            "debit_diff": round((a_amt or 0) - (b_amt or 0), 2),
            "credit_diff": round((a_amt or 0) - (b_amt or 0), 2),
            "match_phase": method,
            "status": _STATUS_LABEL[status_code],
        }

    def _empty_result(self, A: ParsedAct, B: ParsedAct) -> Dict[str, Any]:
        return {
            "status": "completed",
            "total_records": 0,
            "matched": 0,
            "mismatched": 0,
            "not_found_in_source1": 0,
            "not_found_in_source2": 0,
            "data": [],
            "out_of_period": [],
            "header_summary": {
                "owner_act1": A.owner, "owner_act2": B.owner,
                "period_act1": A.period_text, "period_act2": B.period_text,
                "period_mismatch": False, "common_period": "",
                "opening_act1": A.opening, "opening_act2": B.opening, "opening_diff": None,
                "closing_act1": A.closing, "closing_act2": B.closing, "closing_diff": None,
                "turnover_debit_act1": A.turnover_d, "turnover_credit_act1": A.turnover_k,
                "turnover_debit_act2": B.turnover_d, "turnover_credit_act2": B.turnover_k,
            },
            "common_period": "",
            "period_mismatch": False,
            "summary": {
                "total_entries_act1": 0, "total_entries_act2": 0,
                "matched_count": 0, "match_rate": 0, "has_discrepancies": False,
                "auto_detected": A.auto and B.auto,
            },
        }
