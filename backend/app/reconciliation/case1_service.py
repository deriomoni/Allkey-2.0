"""
Case 1 Service: Сверка карточки счета 6010 (1С) с реестром ЭСФ

Matching by date + amount (like Case 2), not by document number.
"""

import pandas as pd
import re
from collections import defaultdict
from typing import Dict, List, Any, Optional
from io import BytesIO
from dataclasses import dataclass


@dataclass
class Transaction6010:
    """Транзакция из карточки счета 6010 (одна строка = одна позиция)"""
    date: str
    counterparty: str
    amount: float
    document: str  # Full doc text for display
    doc_number: str  # Extracted number (e.g. "03191") for grouping
    row_index: int


@dataclass
class Invoice6010:
    """Сгруппированный документ из 6010 (несколько строк = один документ)"""
    date: str
    counterparty: str
    amount: float  # Sum of all line items
    document: str  # Display text
    doc_number: str
    line_count: int


@dataclass
class InvoiceESF:
    """Счет-фактура из реестра ЭСФ"""
    invoice_number: str
    esf_reg_number: str
    issue_date: str
    operation_date: str
    counterparty_bin: Optional[str]
    counterparty_name: str
    amount_with_vat: float
    vat_amount: float
    amount_without_vat: float
    status: str


class Case1Service:
    """
    Case 1: Reconciliation of Account 6010 card (1C) with ESF report

    Matching algorithm (like Case 2):
    1. Parse both files into entries
    2. Group entries by date
    3. For each date, match by amount (prefer matching counterparty names)
    4. Unmatched entries = discrepancies

    Configurable settings:
    - header_row: Row to start reading data (rows before this are skipped)
    - column_mappings: Column indices for each field
    """

    DATE_PATTERN = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
    DOC_NUMBER_PATTERN = re.compile(r'(\d+)\s+от\s+')

    # ESF statuses to skip (cancelled/recalled invoices)
    SKIP_ESF_STATUSES = {'Аннулирован', 'Отозван', 'В ожидании подтверждения отзыва получателя'}

    # Default column positions for 6010 (no header, 0-indexed)
    DEFAULT_6010_DATE_COL = 0
    DEFAULT_6010_COUNTERPARTY_COL = 3
    DEFAULT_6010_AMOUNT_COL = 9

    # Default column positions for ESF (0-indexed)
    DEFAULT_ESF_OPERATION_DATE_COL = 8
    DEFAULT_ESF_RECEIVER_NAME_COL = 3
    DEFAULT_ESF_RECEIVER_BIN_COL = 2
    DEFAULT_ESF_AMOUNT_WITHOUT_VAT_COL = 14
    DEFAULT_ESF_INVOICE_NUMBER_COL = 5
    DEFAULT_ESF_REG_NUMBER_COL = 6
    DEFAULT_ESF_ISSUE_DATE_COL = 7
    DEFAULT_ESF_AMOUNT_WITH_VAT_COL = 11
    DEFAULT_ESF_VAT_AMOUNT_COL = 12
    DEFAULT_ESF_STATUS_COL = 4

    def __init__(
        self,
        account_6010_content: bytes,
        esf_content: bytes,
        account_6010_settings: Dict[str, Any],
        esf_settings: Dict[str, Any],
        tolerance: float = 1.0
    ):
        self.account_6010_content = account_6010_content
        self.esf_content = esf_content
        self.account_6010_settings = account_6010_settings
        self.esf_settings = esf_settings
        self.tolerance = tolerance
        self.doc_filter = account_6010_settings.get('doc_filter', 'Реализация')

    def _get_6010_column_settings(self) -> Dict[str, int]:
        """Extract column settings for 6010 from config"""
        mappings = self.account_6010_settings.get('column_mappings', {})
        return {
            'date_col': mappings.get('date', self.DEFAULT_6010_DATE_COL),
            'counterparty_col': mappings.get('counterparty', self.DEFAULT_6010_COUNTERPARTY_COL),
            'amount_col': mappings.get('amount', self.DEFAULT_6010_AMOUNT_COL),
        }

    def _get_esf_column_settings(self) -> Dict[str, int]:
        """Extract column settings for ESF from config"""
        mappings = self.esf_settings.get('column_mappings', {})
        return {
            'operation_date_col': mappings.get('operation_date', self.DEFAULT_ESF_OPERATION_DATE_COL),
            'receiver_name_col': mappings.get('receiver_name', self.DEFAULT_ESF_RECEIVER_NAME_COL),
            'receiver_bin_col': mappings.get('receiver_bin', self.DEFAULT_ESF_RECEIVER_BIN_COL),
            'amount_without_vat_col': mappings.get('amount_without_vat', self.DEFAULT_ESF_AMOUNT_WITHOUT_VAT_COL),
            'invoice_number_col': mappings.get('invoice_number', self.DEFAULT_ESF_INVOICE_NUMBER_COL),
            'esf_reg_number_col': mappings.get('esf_reg_number', self.DEFAULT_ESF_REG_NUMBER_COL),
            'issue_date_col': mappings.get('issue_date', self.DEFAULT_ESF_ISSUE_DATE_COL),
            'amount_with_vat_col': mappings.get('amount_with_vat', self.DEFAULT_ESF_AMOUNT_WITH_VAT_COL),
            'vat_amount_col': mappings.get('vat_amount', self.DEFAULT_ESF_VAT_AMOUNT_COL),
            'status_col': mappings.get('status', self.DEFAULT_ESF_STATUS_COL),
        }

    def _safe_get(self, row, col_idx):
        """Safely get a cell value from a row by column index"""
        if col_idx < len(row) and pd.notna(row.iloc[col_idx]):
            return row.iloc[col_idx]
        return None

    def parse_account_6010(self) -> List[Transaction6010]:
        """
        Парсит карточку счета 6010 из 1С

        Reads with header=None. Filters rows with valid date and doc_filter keyword.
        No document number parsing - each row is an individual transaction.
        """
        start_row = self.account_6010_settings.get('header_row', 0)
        col = self._get_6010_column_settings()

        df = pd.read_excel(
            BytesIO(self.account_6010_content),
            header=None,
            engine=self._detect_engine(self.account_6010_content)
        )

        transactions = []

        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            # Check date
            cell_date = str(self._safe_get(row, col['date_col']) or '').strip()
            if not self.DATE_PATTERN.match(cell_date):
                continue

            # Check for doc_filter keyword in text column (col 1 by default)
            cell_doc = str(self._safe_get(row, 1) or '')
            if self.doc_filter not in cell_doc:
                continue

            try:
                # Parse counterparty
                cell_cp = str(self._safe_get(row, col['counterparty_col']) or '')
                counterparty = self._parse_counterparty(cell_cp)

                # Parse amount
                amount_raw = self._safe_get(row, col['amount_col'])
                amount = float(amount_raw) if amount_raw is not None else 0.0
                if amount == 0.0:
                    continue

                # Document text for display (first line only)
                doc_display = cell_doc.split('\n')[0][:80] if cell_doc else ''

                # Extract doc number for grouping (e.g. "03191" from "Реализация ТМЗ 03191 от 03.10.2025")
                doc_match = self.DOC_NUMBER_PATTERN.search(cell_doc)
                doc_number = doc_match.group(1) if doc_match else f'row_{idx}'

                transactions.append(Transaction6010(
                    date=cell_date,
                    counterparty=counterparty,
                    amount=amount,
                    document=doc_display,
                    doc_number=doc_number,
                    row_index=idx
                ))
            except Exception:
                continue

        return transactions

    def parse_esf(self) -> List[InvoiceESF]:
        """
        Парсит реестр счетов-фактур из ИС ЭСФ

        Column positions are configurable via settings.
        Default header_row=2 (skip row 0 = summary, row 1 = headers)

        Filters:
        - Skips annulled/recalled invoices (Аннулирован, Отозван)
        - Skips negative amounts (credit notes)
        """
        start_row = self.esf_settings.get('header_row', 2)
        col = self._get_esf_column_settings()

        df = pd.read_excel(
            BytesIO(self.esf_content),
            header=None,
            engine=self._detect_engine(self.esf_content)
        )

        invoices = []

        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            try:
                # Check status - skip cancelled/recalled invoices
                esf_status = str(self._safe_get(row, col['status_col']) or '')
                if esf_status in self.SKIP_ESF_STATUSES:
                    continue

                op_date_raw = self._safe_get(row, col['operation_date_col'])
                op_date = self._format_date(op_date_raw)
                if not op_date:
                    continue

                # Parse amount and skip negative (credit notes/returns)
                amount_without_vat = float(self._safe_get(row, col['amount_without_vat_col']) or 0)
                if amount_without_vat <= 0:
                    continue

                invoice = InvoiceESF(
                    invoice_number=str(self._safe_get(row, col['invoice_number_col']) or ''),
                    esf_reg_number=str(self._safe_get(row, col['esf_reg_number_col']) or ''),
                    issue_date=self._format_date(self._safe_get(row, col['issue_date_col'])),
                    operation_date=op_date,
                    counterparty_bin=str(self._safe_get(row, col['receiver_bin_col'])) if self._safe_get(row, col['receiver_bin_col']) else None,
                    counterparty_name=self._normalize_name(str(self._safe_get(row, col['receiver_name_col']) or '')),
                    amount_with_vat=float(self._safe_get(row, col['amount_with_vat_col']) or 0),
                    vat_amount=float(self._safe_get(row, col['vat_amount_col']) or 0),
                    amount_without_vat=amount_without_vat,
                    status=esf_status
                )
                invoices.append(invoice)
            except Exception:
                continue

        return invoices

    def _group_6010_transactions(self, transactions: List[Transaction6010]) -> List[Invoice6010]:
        """
        Group individual 6010 line items into invoice-level documents.

        The 6010 card has one row per product/service line, but an ESF invoice
        is the total for all lines. We group by (date, doc_number) and sum amounts
        to get invoice-level totals that can match against ESF.
        """
        groups: Dict[tuple, List[Transaction6010]] = defaultdict(list)
        for t in transactions:
            groups[(t.date, t.doc_number)].append(t)

        invoices = []
        for (date, doc_number), items in groups.items():
            total_amount = sum(t.amount for t in items)
            # Use counterparty from the first item (all items in same doc share counterparty)
            counterparty = items[0].counterparty
            doc_display = items[0].document

            invoices.append(Invoice6010(
                date=date,
                counterparty=counterparty,
                amount=round(total_amount, 2),
                document=doc_display,
                doc_number=doc_number,
                line_count=len(items)
            ))

        return invoices

    def reconcile(self) -> Dict[str, Any]:
        """
        Match 6010 invoices against ESF by amount + counterparty name.

        Key insight: 6010 document date and ESF operation date often differ
        (1C entry date vs actual delivery date), so we use cross-date matching.

        Algorithm:
        1. Parse 6010 line items and GROUP by doc number → invoice-level totals
        2. Parse ESF invoices
        3. Phase 1: Same-date matching (exact amount + name, then amount only)
        4. Phase 2: Cross-date matching for remaining (amount + name across all dates)
        5. Unmatched = discrepancies
        """
        raw_entries_6010 = self.parse_account_6010()
        invoices_esf = self.parse_esf()

        # Group line items into invoice-level documents
        entries_6010 = self._group_6010_transactions(raw_entries_6010)

        if not entries_6010 and not invoices_esf:
            return {
                'status': 'completed',
                'total_records': 0,
                'matched': 0,
                'mismatched': 0,
                'not_found_in_source1': 0,
                'not_found_in_source2': 0,
                'data': [],
                'summary': {
                    'total_1c_entries': 0,
                    'total_esf_invoices': 0,
                    'matched_count': 0,
                    'match_rate': 0,
                    'total_1c_amount': 0,
                    'total_esf_amount': 0,
                    'total_difference': 0,
                    'has_discrepancies': False
                }
            }

        # Track which entries have been matched (by index in their respective lists)
        matched_6010: set = set()
        matched_esf: set = set()
        results = []

        # Build index by date for same-date matching
        by_date_6010: Dict[str, List[int]] = defaultdict(list)
        by_date_esf: Dict[str, List[int]] = defaultdict(list)

        for i, e in enumerate(entries_6010):
            by_date_6010[e.date].append(i)
        for j, inv in enumerate(invoices_esf):
            by_date_esf[inv.operation_date].append(j)

        all_dates = sorted(set(by_date_6010.keys()) | set(by_date_esf.keys()))

        # ===== Phase 1: Same-date matching =====
        for date in all_dates:
            our_idxs = by_date_6010.get(date, [])
            esf_idxs = by_date_esf.get(date, [])

            # Pass 1a: exact amount + similar name (same date)
            for i in our_idxs:
                if i in matched_6010:
                    continue
                e = entries_6010[i]
                for j in esf_idxs:
                    if j in matched_esf:
                        continue
                    inv = invoices_esf[j]
                    if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                        if self._similar_names(e.counterparty, inv.counterparty_name):
                            matched_6010.add(i)
                            matched_esf.add(j)
                            results.append(self._make_matched_result(e, inv, date))
                            break

            # Pass 1b: exact amount only (same date, no name check)
            for i in our_idxs:
                if i in matched_6010:
                    continue
                e = entries_6010[i]
                for j in esf_idxs:
                    if j in matched_esf:
                        continue
                    inv = invoices_esf[j]
                    if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                        matched_6010.add(i)
                        matched_esf.add(j)
                        results.append(self._make_matched_result(e, inv, date))
                        break

        # ===== Phase 2: Cross-date matching (for remaining unmatched) =====
        # 6010 and ESF dates often differ, so match by amount + name across all dates
        unmatched_6010 = [i for i in range(len(entries_6010)) if i not in matched_6010]
        unmatched_esf = [j for j in range(len(invoices_esf)) if j not in matched_esf]

        # Pass 2a: exact amount + similar name (any date)
        for i in unmatched_6010:
            if i in matched_6010:
                continue
            e = entries_6010[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                    if self._similar_names(e.counterparty, inv.counterparty_name):
                        matched_6010.add(i)
                        matched_esf.add(j)
                        results.append(self._make_matched_result(e, inv, e.date))
                        break

        # Pass 2b: exact amount only (any date, no name check)
        unmatched_6010 = [i for i in unmatched_6010 if i not in matched_6010]
        unmatched_esf = [j for j in unmatched_esf if j not in matched_esf]

        for i in unmatched_6010:
            if i in matched_6010:
                continue
            e = entries_6010[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                    matched_6010.add(i)
                    matched_esf.add(j)
                    results.append(self._make_matched_result(e, inv, e.date))
                    break

        # Pass 2c: amount within 1% + similar name (any date, handles rounding)
        unmatched_6010 = [i for i in range(len(entries_6010)) if i not in matched_6010]
        unmatched_esf = [j for j in range(len(invoices_esf)) if j not in matched_esf]

        for i in unmatched_6010:
            if i in matched_6010:
                continue
            e = entries_6010[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if self._similar_names(e.counterparty, inv.counterparty_name):
                    max_amount = max(e.amount, inv.amount_without_vat)
                    if max_amount > 0 and abs(e.amount - inv.amount_without_vat) < max_amount * 0.01:
                        matched_6010.add(i)
                        matched_esf.add(j)
                        results.append({
                            'date': e.date,
                            'document': e.document,
                            'counterparty_6010': e.counterparty,
                            'recipient_esf': inv.counterparty_name,
                            'amount_6010': e.amount,
                            'amount_esf': round(inv.amount_without_vat, 2),
                            'esf_number': inv.invoice_number,
                            'esf_reg_number': inv.esf_reg_number,
                            'difference': round(e.amount - inv.amount_without_vat, 2),
                            'status': 'Расхождение'
                        })
                        break

        # ===== Collect unmatched entries =====
        for i in range(len(entries_6010)):
            if i not in matched_6010:
                e = entries_6010[i]
                results.append({
                    'date': e.date,
                    'document': e.document,
                    'counterparty_6010': e.counterparty,
                    'recipient_esf': None,
                    'amount_6010': e.amount,
                    'amount_esf': None,
                    'esf_number': None,
                    'esf_reg_number': None,
                    'difference': e.amount,
                    'status': 'Не найдено в ЭСФ'
                })

        for j in range(len(invoices_esf)):
            if j not in matched_esf:
                inv = invoices_esf[j]
                results.append({
                    'date': inv.operation_date,
                    'document': None,
                    'counterparty_6010': None,
                    'recipient_esf': inv.counterparty_name,
                    'amount_6010': None,
                    'amount_esf': round(inv.amount_without_vat, 2),
                    'esf_number': inv.invoice_number,
                    'esf_reg_number': inv.esf_reg_number,
                    'difference': round(-inv.amount_without_vat, 2),
                    'status': 'Не найдено в 6010'
                })

        # Sort results by date
        results.sort(key=lambda r: r['date'].split('.')[::-1])

        # Statistics
        matched_count = sum(1 for r in results if r['status'] == 'Совпадает')
        mismatched_count = sum(1 for r in results if r['status'] == 'Расхождение')
        not_found_6010 = sum(1 for r in results if r['status'] == 'Не найдено в ЭСФ')
        not_found_esf = sum(1 for r in results if r['status'] == 'Не найдено в 6010')

        total_1c = sum(e.amount for e in entries_6010)
        total_esf = sum(inv.amount_without_vat for inv in invoices_esf)
        max_entries = max(len(entries_6010), len(invoices_esf))

        return {
            'status': 'completed',
            'total_records': len(results),
            'matched': matched_count,
            'mismatched': mismatched_count,
            'not_found_in_source1': not_found_6010,
            'not_found_in_source2': not_found_esf,
            'data': results,
            'summary': {
                'total_1c_entries': len(entries_6010),
                'total_esf_invoices': len(invoices_esf),
                'matched_count': matched_count,
                'match_rate': round(matched_count / max_entries * 100, 1) if max_entries > 0 else 0,
                'total_1c_amount': round(total_1c, 2),
                'total_esf_amount': round(total_esf, 2),
                'total_difference': round(total_1c - total_esf, 2),
                'has_discrepancies': not_found_6010 > 0 or not_found_esf > 0 or mismatched_count > 0
            }
        }

    def _make_matched_result(self, e: Invoice6010, inv: InvoiceESF, date: str) -> Dict:
        return {
            'date': date,
            'document': e.document,
            'counterparty_6010': e.counterparty,
            'recipient_esf': inv.counterparty_name,
            'amount_6010': e.amount,
            'amount_esf': round(inv.amount_without_vat, 2),
            'esf_number': inv.invoice_number,
            'esf_reg_number': inv.esf_reg_number,
            'difference': 0,
            'status': 'Совпадает'
        }

    # ==================== Helper Methods ====================

    def _detect_engine(self, content: bytes) -> str:
        if len(content) < 4:
            raise ValueError("Файл слишком маленький или пустой")
        if content[:2] == b'PK':
            return 'openpyxl'
        if content[:2] == b'\xd0\xcf':
            return 'xlrd'
        raise ValueError("Неподдерживаемый формат файла")

    def _parse_counterparty(self, text: str) -> str:
        """Parse counterparty name from multiline cell text"""
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or 'Головное подразделение' in line or '<...>' in line:
                continue
            if 'Договор' in line:
                continue
            if 'Основная номенклатурная' in line:
                continue
            return self._normalize_name(line)
        return ''

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r'[«»""\'"]', '', name)
        patterns = [
            r'\bтоо\b', r'\bооо\b', r'\bао\b', r'\bпао\b', r'\bзао\b',
            r'\bсп\b', r'\bллп\b', r'\bllp\b', r'\bltd\b',
            r'\bтоварищество с ограниченной ответственностью\b'
        ]
        for p in patterns:
            name = re.sub(p, '', name, flags=re.IGNORECASE)
        return ' '.join(name.split())

    def _format_date(self, value) -> str:
        if pd.isna(value):
            return ''
        if isinstance(value, str):
            if re.match(r'\d{2}\.\d{2}\.\d{4}', value):
                return value[:10]
            return value
        if hasattr(value, 'strftime'):
            return value.strftime('%d.%m.%Y')
        return str(value)

    def _similar_names(self, name1: str, name2: str) -> bool:
        n1 = self._normalize_name(name1)
        n2 = self._normalize_name(name2)

        if n1 == n2:
            return True
        if n1 in n2 or n2 in n1:
            return True

        words1 = {w for w in n1.split() if len(w) > 2}
        words2 = {w for w in n2.split() if len(w) > 2}
        if words1 and words2:
            intersection = words1 & words2
            min_len = min(len(words1), len(words2))
            if len(intersection) >= min_len * 0.5:
                return True

        return False
