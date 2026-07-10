"""
Case 3 Service: Сверка карточки счета 3310 (1С) с реестром ЭСФ (входящие)

Matching by date + amount (like Case 1), for incoming invoices (Поступление).
Shows ТРУ instead of counterparty, and both sender + receiver from ESF.
"""

import pandas as pd
import re
from collections import defaultdict
from typing import Dict, List, Any, Optional
from io import BytesIO
from dataclasses import dataclass


@dataclass
class Transaction3310:
    """Транзакция из карточки счета 3310 (одна строка = одна позиция)"""
    date: str
    tru: str  # ТРУ (товары, работы, услуги)
    amount: float
    document: str
    doc_number: str
    row_index: int


@dataclass
class Invoice3310:
    """Сгруппированный документ из 3310 (несколько строк = один документ)"""
    date: str
    tru: str
    amount: float
    document: str
    doc_number: str
    line_count: int


@dataclass
class InvoiceESF:
    """Счет-фактура из реестра ЭСФ (входящая)"""
    invoice_number: str
    esf_reg_number: str
    issue_date: str
    operation_date: str
    sender_name: str
    sender_bin: Optional[str]
    receiver_name: str
    receiver_bin: Optional[str]
    amount_with_vat: float
    vat_amount: float
    amount_without_vat: float
    status: str


class Case3Service:
    """
    Case 3: Reconciliation of Account 3310 card (1C) with incoming ESF report

    Like Case 1 but for incoming invoices (Поступление).
    Shows ТРУ from 1C and both sender/receiver from ESF.
    """

    DATE_PATTERN = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
    DOC_NUMBER_PATTERN = re.compile(r'(\d+)\s+от\s+')

    SKIP_ESF_STATUSES = {'Аннулирован', 'Отозван', 'В ожидании подтверждения отзыва получателя'}

    # Default column positions for 3310 (0-indexed)
    DEFAULT_3310_DATE_COL = 0
    DEFAULT_3310_TRU_COL = 3
    DEFAULT_3310_AMOUNT_COL = 9

    # Default column positions for ESF (0-indexed)
    DEFAULT_ESF_OPERATION_DATE_COL = 8
    DEFAULT_ESF_SENDER_NAME_COL = 1
    DEFAULT_ESF_SENDER_BIN_COL = 0
    DEFAULT_ESF_RECEIVER_NAME_COL = 3
    DEFAULT_ESF_RECEIVER_BIN_COL = 2
    DEFAULT_ESF_AMOUNT_WITHOUT_VAT_COL = 11
    DEFAULT_ESF_INVOICE_NUMBER_COL = 5
    DEFAULT_ESF_REG_NUMBER_COL = 6
    DEFAULT_ESF_ISSUE_DATE_COL = 7
    DEFAULT_ESF_AMOUNT_WITH_VAT_COL = 11
    DEFAULT_ESF_VAT_AMOUNT_COL = 12
    DEFAULT_ESF_STATUS_COL = 4

    def __init__(
        self,
        account_3310_content: bytes,
        esf_content: bytes,
        account_3310_settings: Dict[str, Any],
        esf_settings: Dict[str, Any],
        tolerance: float = 1.0
    ):
        self.account_3310_content = account_3310_content
        self.esf_content = esf_content
        self.account_3310_settings = account_3310_settings
        self.esf_settings = esf_settings
        self.tolerance = tolerance
        self.doc_filter = account_3310_settings.get('doc_filter', 'Поступление')

    def _get_3310_column_settings(self) -> Dict[str, int]:
        mappings = self.account_3310_settings.get('column_mappings', {})
        return {
            'date_col': mappings.get('date', self.DEFAULT_3310_DATE_COL),
            'tru_col': mappings.get('tru', self.DEFAULT_3310_TRU_COL),
            'amount_col': mappings.get('amount', self.DEFAULT_3310_AMOUNT_COL),
        }

    def _get_esf_column_settings(self) -> Dict[str, int]:
        mappings = self.esf_settings.get('column_mappings', {})
        return {
            'operation_date_col': mappings.get('operation_date', self.DEFAULT_ESF_OPERATION_DATE_COL),
            'sender_name_col': mappings.get('sender_name', self.DEFAULT_ESF_SENDER_NAME_COL),
            'sender_bin_col': mappings.get('sender_bin', self.DEFAULT_ESF_SENDER_BIN_COL),
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
        if col_idx < len(row) and pd.notna(row.iloc[col_idx]):
            return row.iloc[col_idx]
        return None

    def parse_account_3310(self) -> List[Transaction3310]:
        """
        Парсит карточку счета 3310 из 1С

        Reads with header=None. Filters rows with valid date and doc_filter keyword.
        """
        start_row = self.account_3310_settings.get('header_row', 0)
        col = self._get_3310_column_settings()

        df = pd.read_excel(
            BytesIO(self.account_3310_content),
            header=None,
            engine=self._detect_engine(self.account_3310_content)
        )

        transactions = []

        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            cell_date = str(self._safe_get(row, col['date_col']) or '').strip()
            if not self.DATE_PATTERN.match(cell_date):
                continue

            # Check for doc_filter keyword in text column (col 1 by default)
            cell_doc = str(self._safe_get(row, 1) or '')
            if self.doc_filter not in cell_doc:
                continue

            try:
                # Parse ТРУ
                cell_tru = str(self._safe_get(row, col['tru_col']) or '')
                tru = cell_tru.split('\n')[0].strip()[:100] if cell_tru else ''

                # Parse amount
                amount_raw = self._safe_get(row, col['amount_col'])
                amount = float(amount_raw) if amount_raw is not None else 0.0
                if amount == 0.0:
                    continue

                doc_display = cell_doc.split('\n')[0][:80] if cell_doc else ''

                doc_match = self.DOC_NUMBER_PATTERN.search(cell_doc)
                doc_number = doc_match.group(1) if doc_match else f'row_{idx}'

                transactions.append(Transaction3310(
                    date=cell_date,
                    tru=tru,
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
        Парсит реестр счетов-фактур из ИС ЭСФ (входящие)

        Includes both sender and receiver information.
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
                esf_status = str(self._safe_get(row, col['status_col']) or '')
                if esf_status in self.SKIP_ESF_STATUSES:
                    continue

                op_date_raw = self._safe_get(row, col['operation_date_col'])
                op_date = self._format_date(op_date_raw)
                if not op_date:
                    continue

                amount_without_vat = float(self._safe_get(row, col['amount_without_vat_col']) or 0)
                if amount_without_vat <= 0:
                    continue

                invoice = InvoiceESF(
                    invoice_number=str(self._safe_get(row, col['invoice_number_col']) or ''),
                    esf_reg_number=str(self._safe_get(row, col['esf_reg_number_col']) or ''),
                    issue_date=self._format_date(self._safe_get(row, col['issue_date_col'])),
                    operation_date=op_date,
                    sender_name=self._normalize_name(str(self._safe_get(row, col['sender_name_col']) or '')),
                    sender_bin=str(self._safe_get(row, col['sender_bin_col'])) if self._safe_get(row, col['sender_bin_col']) else None,
                    receiver_name=self._normalize_name(str(self._safe_get(row, col['receiver_name_col']) or '')),
                    receiver_bin=str(self._safe_get(row, col['receiver_bin_col'])) if self._safe_get(row, col['receiver_bin_col']) else None,
                    amount_with_vat=float(self._safe_get(row, col['amount_with_vat_col']) or 0),
                    vat_amount=float(self._safe_get(row, col['vat_amount_col']) or 0),
                    amount_without_vat=amount_without_vat,
                    status=esf_status
                )
                invoices.append(invoice)
            except Exception:
                continue

        return invoices

    def _group_3310_transactions(self, transactions: List[Transaction3310]) -> List[Invoice3310]:
        """Group individual 3310 line items into invoice-level documents."""
        groups: Dict[tuple, List[Transaction3310]] = defaultdict(list)
        for t in transactions:
            groups[(t.date, t.doc_number)].append(t)

        invoices = []
        for (date, doc_number), items in groups.items():
            total_amount = sum(t.amount for t in items)
            tru = items[0].tru
            doc_display = items[0].document

            invoices.append(Invoice3310(
                date=date,
                tru=tru,
                amount=round(total_amount, 2),
                document=doc_display,
                doc_number=doc_number,
                line_count=len(items)
            ))

        return invoices

    def reconcile(self) -> Dict[str, Any]:
        """
        Match 3310 invoices against ESF by amount + sender name.

        Algorithm:
        1. Parse 3310 line items and group by doc number
        2. Parse ESF invoices
        3. Phase 1: Same-date matching (amount + sender name, then amount only)
        4. Phase 2: Cross-date matching for remaining
        5. Unmatched = discrepancies
        """
        raw_entries_3310 = self.parse_account_3310()
        invoices_esf = self.parse_esf()

        entries_3310 = self._group_3310_transactions(raw_entries_3310)

        if not entries_3310 and not invoices_esf:
            return {
                'status': 'completed',
                'total_records': 0,
                'matched': 0,
                'mismatched': 0,
                'not_found_in_source1': 0,
                'not_found_in_source2': 0,
                'data': [],
                'summary': {
                    'total_3310_entries': 0,
                    'total_esf_invoices': 0,
                    'matched_count': 0,
                    'match_rate': 0,
                    'total_3310_amount': 0,
                    'total_esf_amount': 0,
                    'total_difference': 0,
                    'has_discrepancies': False
                }
            }

        matched_3310: set = set()
        matched_esf: set = set()
        results = []

        by_date_3310: Dict[str, List[int]] = defaultdict(list)
        by_date_esf: Dict[str, List[int]] = defaultdict(list)

        for i, e in enumerate(entries_3310):
            by_date_3310[e.date].append(i)
        for j, inv in enumerate(invoices_esf):
            by_date_esf[inv.operation_date].append(j)

        all_dates = sorted(set(by_date_3310.keys()) | set(by_date_esf.keys()))

        # ===== Phase 1: Same-date matching =====
        for date in all_dates:
            our_idxs = by_date_3310.get(date, [])
            esf_idxs = by_date_esf.get(date, [])

            # Pass 1a: exact amount + similar sender name (same date)
            for i in our_idxs:
                if i in matched_3310:
                    continue
                e = entries_3310[i]
                for j in esf_idxs:
                    if j in matched_esf:
                        continue
                    inv = invoices_esf[j]
                    if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                        if self._similar_names(e.tru, inv.sender_name):
                            matched_3310.add(i)
                            matched_esf.add(j)
                            results.append(self._make_matched_result(e, inv, date))
                            break

            # Pass 1b: exact amount only (same date)
            for i in our_idxs:
                if i in matched_3310:
                    continue
                e = entries_3310[i]
                for j in esf_idxs:
                    if j in matched_esf:
                        continue
                    inv = invoices_esf[j]
                    if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                        matched_3310.add(i)
                        matched_esf.add(j)
                        results.append(self._make_matched_result(e, inv, date))
                        break

        # ===== Phase 2: Cross-date matching =====
        unmatched_3310 = [i for i in range(len(entries_3310)) if i not in matched_3310]
        unmatched_esf = [j for j in range(len(invoices_esf)) if j not in matched_esf]

        # Pass 2a: exact amount + similar name (any date)
        for i in unmatched_3310:
            if i in matched_3310:
                continue
            e = entries_3310[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                    if self._similar_names(e.tru, inv.sender_name):
                        matched_3310.add(i)
                        matched_esf.add(j)
                        results.append(self._make_matched_result(e, inv, e.date))
                        break

        # Pass 2b: exact amount only (any date)
        unmatched_3310 = [i for i in unmatched_3310 if i not in matched_3310]
        unmatched_esf = [j for j in unmatched_esf if j not in matched_esf]

        for i in unmatched_3310:
            if i in matched_3310:
                continue
            e = entries_3310[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if abs(e.amount - inv.amount_without_vat) <= self.tolerance:
                    matched_3310.add(i)
                    matched_esf.add(j)
                    results.append(self._make_matched_result(e, inv, e.date))
                    break

        # Pass 2c: amount within 1% + similar name (any date)
        unmatched_3310 = [i for i in range(len(entries_3310)) if i not in matched_3310]
        unmatched_esf = [j for j in range(len(invoices_esf)) if j not in matched_esf]

        for i in unmatched_3310:
            if i in matched_3310:
                continue
            e = entries_3310[i]
            for j in unmatched_esf:
                if j in matched_esf:
                    continue
                inv = invoices_esf[j]
                if self._similar_names(e.tru, inv.sender_name):
                    max_amount = max(e.amount, inv.amount_without_vat)
                    if max_amount > 0 and abs(e.amount - inv.amount_without_vat) < max_amount * 0.01:
                        matched_3310.add(i)
                        matched_esf.add(j)
                        results.append({
                            'date': e.date,
                            'document': e.document,
                            'tru': e.tru,
                            'sender_esf': inv.sender_name,
                            'recipient_esf': inv.receiver_name,
                            'amount_3310': e.amount,
                            'amount_esf': round(inv.amount_without_vat, 2),
                            'esf_number': inv.invoice_number,
                            'esf_reg_number': inv.esf_reg_number,
                            'difference': round(e.amount - inv.amount_without_vat, 2),
                            'status': 'Расхождение'
                        })
                        break

        # ===== Collect unmatched entries =====
        for i in range(len(entries_3310)):
            if i not in matched_3310:
                e = entries_3310[i]
                results.append({
                    'date': e.date,
                    'document': e.document,
                    'tru': e.tru,
                    'sender_esf': None,
                    'recipient_esf': None,
                    'amount_3310': e.amount,
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
                    'tru': None,
                    'sender_esf': inv.sender_name,
                    'recipient_esf': inv.receiver_name,
                    'amount_3310': None,
                    'amount_esf': round(inv.amount_without_vat, 2),
                    'esf_number': inv.invoice_number,
                    'esf_reg_number': inv.esf_reg_number,
                    'difference': round(-inv.amount_without_vat, 2),
                    'status': 'Не найдено в 3310'
                })

        results.sort(key=lambda r: r['date'].split('.')[::-1])

        matched_count = sum(1 for r in results if r['status'] == 'Совпадает')
        mismatched_count = sum(1 for r in results if r['status'] == 'Расхождение')
        not_found_3310 = sum(1 for r in results if r['status'] == 'Не найдено в ЭСФ')
        not_found_esf = sum(1 for r in results if r['status'] == 'Не найдено в 3310')

        total_3310 = sum(e.amount for e in entries_3310)
        total_esf = sum(inv.amount_without_vat for inv in invoices_esf)
        max_entries = max(len(entries_3310), len(invoices_esf))

        return {
            'status': 'completed',
            'total_records': len(results),
            'matched': matched_count,
            'mismatched': mismatched_count,
            'not_found_in_source1': not_found_3310,
            'not_found_in_source2': not_found_esf,
            'data': results,
            'summary': {
                'total_3310_entries': len(entries_3310),
                'total_esf_invoices': len(invoices_esf),
                'matched_count': matched_count,
                'match_rate': round(matched_count / max_entries * 100, 1) if max_entries > 0 else 0,
                'total_3310_amount': round(total_3310, 2),
                'total_esf_amount': round(total_esf, 2),
                'total_difference': round(total_3310 - total_esf, 2),
                'has_discrepancies': not_found_3310 > 0 or not_found_esf > 0 or mismatched_count > 0
            }
        }

    def _make_matched_result(self, e: Invoice3310, inv: InvoiceESF, date: str) -> Dict:
        return {
            'date': date,
            'document': e.document,
            'tru': e.tru,
            'sender_esf': inv.sender_name,
            'recipient_esf': inv.receiver_name,
            'amount_3310': e.amount,
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
