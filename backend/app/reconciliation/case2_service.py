"""
Case 2: Reconciliation of mutual settlement acts between counterparties
Matches by (date, amount, op_type) - NOT by document number!
"""

import pandas as pd
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from io import BytesIO

from .parse_document import parse_document_field


@dataclass
class ActEntry:
    """Entry from settlement act"""
    date: str  # Normalized to DD.MM.YY format
    document: str
    debit: float
    credit: float
    amount: float  # abs value for matching
    op_type: str   # 'товар', 'оплата', 'прочее'
    row_index: int
    doc_number: Optional[str] = None  # Parsed document number
    extra_number: Optional[str] = None  # Extra number (e.g. "вх. 476")


class Case2Service:
    """
    Case 2: Reconciliation of mutual settlement acts between counterparties

    Key differences from document-based matching:
    - Each side has different document numbers ("Поступление 00000003015" vs "Реализация 28")
    - Match by: (date, amount, op_type) instead of document number
    - Debit/Credit are mirrored between counterparties
    - Skip счет-фактура rows (they duplicate info)

    Configurable settings:
    - start_row: Row to start reading data (0-indexed, default: 0 = auto-detect)
    - date_col: Column index for date (default: 1)
    - document_col: Column index for document (default: 2)
    - debit_col: Column index for debit (default: 4)
    - credit_col: Column index for credit (default: 5)
    """

    # Default column positions for standard 1C act format
    DEFAULT_DATE_COL = 1
    DEFAULT_DOCUMENT_COL = 2
    DEFAULT_DEBIT_COL = 4
    DEFAULT_CREDIT_COL = 5

    def __init__(
        self,
        our_act_content: bytes,
        counterparty_act_content: bytes,
        our_act_settings: Dict[str, Any],
        counterparty_act_settings: Dict[str, Any]
    ):
        self.our_act_content = our_act_content
        self.counterparty_act_content = counterparty_act_content
        self.our_act_settings = our_act_settings
        self.counterparty_act_settings = counterparty_act_settings
        # Pattern for DD.MM.YY format
        self.date_pattern_short = re.compile(r'^\d{2}\.\d{2}\.\d{2}$')
        # Pattern for YYYY-MM-DD (datetime)
        self.date_pattern_iso = re.compile(r'^\d{4}-\d{2}-\d{2}')
        # Patterns for extracting dates from text
        self.date_extract_patterns = {
            'DD.MM.YYYY': re.compile(r'(\d{2}\.\d{2}\.\d{4})'),
            'DD.MM.YY': re.compile(r'(\d{2}\.\d{2}\.\d{2})(?!\d)'),
        }

    def _parse_date(self, value: Any) -> Optional[str]:
        """
        Parse date from various formats and normalize to DD.MM.YY
        Supports: DD.MM.YY, YYYY-MM-DD, datetime objects
        """
        if pd.isna(value):
            return None

        # Handle datetime objects (pandas Timestamp)
        if isinstance(value, (datetime, pd.Timestamp)):
            return value.strftime('%d.%m.%y')

        str_value = str(value).strip()

        # DD.MM.YY format
        if self.date_pattern_short.match(str_value):
            return str_value

        # DD.MM.YYYY format (4-digit year)
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', str_value):
            try:
                dt = datetime.strptime(str_value, '%d.%m.%Y')
                return dt.strftime('%d.%m.%y')
            except ValueError:
                pass

        # YYYY-MM-DD or YYYY-MM-DD HH:MM:SS format
        if self.date_pattern_iso.match(str_value):
            try:
                # Parse ISO date
                date_part = str_value.split()[0]  # Take only date part
                dt = datetime.strptime(date_part, '%Y-%m-%d')
                return dt.strftime('%d.%m.%y')
            except ValueError:
                pass

        return None

    def _extract_date_from_text(self, text: Any, date_format: str) -> Optional[str]:
        """
        Extract date from text using regex for the specified format.
        Returns normalized date in DD.MM.YY format.
        """
        if pd.isna(text):
            return None

        str_value = str(text).strip()
        if not str_value:
            return None

        pattern = self.date_extract_patterns.get(date_format)
        if not pattern:
            return None

        match = pattern.search(str_value)
        if not match:
            return None

        date_str = match.group(1)

        if date_format == 'DD.MM.YYYY':
            try:
                dt = datetime.strptime(date_str, '%d.%m.%Y')
                return dt.strftime('%d.%m.%y')
            except ValueError:
                return None
        elif date_format == 'DD.MM.YY':
            try:
                dt = datetime.strptime(date_str, '%d.%m.%y')
                return dt.strftime('%d.%m.%y')
            except ValueError:
                return None

        return None

    def _parse_number(self, value: Any) -> float:
        """
        Parse number from various formats
        Supports: 8520, 8 520, 8 520,00, 8,520.00
        """
        if pd.isna(value):
            return 0.0

        # Already a number
        if isinstance(value, (int, float)):
            return float(value)

        str_value = str(value).strip()
        if not str_value:
            return 0.0

        try:
            # Remove spaces (thousand separators)
            str_value = str_value.replace(' ', '').replace('\u00a0', '')

            # Handle comma as decimal separator (European format: 8520,00)
            # vs comma as thousand separator (US format: 8,520.00)
            if ',' in str_value and '.' in str_value:
                # Both present: assume US format (1,234.56)
                str_value = str_value.replace(',', '')
            elif ',' in str_value:
                # Only comma: check if it's decimal separator
                # If exactly 2 digits after comma, it's decimal
                parts = str_value.split(',')
                if len(parts) == 2 and len(parts[1]) <= 2:
                    str_value = str_value.replace(',', '.')
                else:
                    # It's a thousand separator
                    str_value = str_value.replace(',', '')

            return float(str_value)
        except (ValueError, TypeError):
            return 0.0

    def _get_column_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Extract column settings from config, using defaults if not specified"""
        mappings = settings.get('column_mappings', {})
        result = {
            'date_col': mappings.get('date', self.DEFAULT_DATE_COL),
            'document_col': mappings.get('document', self.DEFAULT_DOCUMENT_COL),
            'debit_col': mappings.get('debit', self.DEFAULT_DEBIT_COL),
            'credit_col': mappings.get('credit', self.DEFAULT_CREDIT_COL),
            'date_extract_from_text': settings.get('date_extract_from_text', False),
            'date_format': settings.get('date_format'),
            'date_source_column': settings.get('date_source_column'),
        }
        return result

    def parse_act(self, content: bytes, settings: Dict[str, Any]) -> List[ActEntry]:
        """
        Parse settlement act with configurable column positions

        Supports multiple date formats (DD.MM.YY, YYYY-MM-DD, datetime)
        and number formats (8520, 8 520, 8 520,00)
        """
        # Get start row (header_row from frontend settings)
        start_row = settings.get('header_row', 0)
        col_settings = self._get_column_settings(settings)

        date_col = col_settings['date_col']
        document_col = col_settings['document_col']
        debit_col = col_settings['debit_col']
        credit_col = col_settings['credit_col']
        date_extract_from_text = col_settings.get('date_extract_from_text', False)
        date_format = col_settings.get('date_format')
        date_source_column = col_settings.get('date_source_column')

        df = pd.read_excel(BytesIO(content), header=None)
        entries = []

        for idx, row in df.iterrows():
            # Skip rows before start_row if specified
            if start_row > 0 and idx < start_row:
                continue

            # Parse date: either from dedicated column or extract from text
            if date_extract_from_text and date_format is not None and date_source_column is not None:
                # Extract date from text in the specified source column
                if date_source_column >= len(row):
                    continue
                parsed_date = self._extract_date_from_text(row.iloc[date_source_column], date_format)
            else:
                # Standard: read from dedicated date column
                if date_col >= len(row):
                    continue
                parsed_date = self._parse_date(row.iloc[date_col])

            if not parsed_date:
                continue

            # Safely get document and parse its components
            doc = ''
            doc_number = None
            extra_number = None
            if document_col < len(row) and pd.notna(row.iloc[document_col]):
                doc = str(row.iloc[document_col])
                parsed_doc = parse_document_field(doc)
                doc_number = parsed_doc.doc_number
                extra_number = parsed_doc.extra_number

            # SKIP rows that START with счет-фактура (they duplicate info in file 1)
            # But keep rows where счет-фактура is mentioned later in the text (file 2 format)
            doc_first_line = doc.split('\n')[0].lower().strip()
            if doc_first_line.startswith('счет-фактура') or doc_first_line.startswith('электронный счет-фактура'):
                continue

            # Parse debit and credit using flexible number parser
            debit = 0.0
            credit = 0.0
            if debit_col < len(row):
                debit = self._parse_number(row.iloc[debit_col])
            if credit_col < len(row):
                credit = self._parse_number(row.iloc[credit_col])

            # Skip rows with no amounts (like "Сальдо на начало")
            if debit == 0.0 and credit == 0.0:
                continue

            amount = debit if debit > 0 else credit
            op_type = self._determine_op_type(doc)

            entries.append(ActEntry(
                date=parsed_date,
                document=doc,
                debit=debit,
                credit=credit,
                amount=amount,
                op_type=op_type,
                row_index=idx,
                doc_number=doc_number,
                extra_number=extra_number,
            ))

        return entries

    def _determine_op_type(self, doc: str) -> str:
        """Determine operation type from document text"""
        doc_lower = doc.lower()

        if 'поступление' in doc_lower or 'реализация' in doc_lower:
            return 'товар'
        elif 'платежное' in doc_lower or 'оплата' in doc_lower:
            return 'оплата'
        elif 'корректировка' in doc_lower:
            return 'корректировка'
        elif 'возврат' in doc_lower:
            return 'возврат'
        return 'прочее'

    def reconcile(self) -> Dict[str, Any]:
        """
        Reconcile by grouping entries by date and matching by amount.

        New Logic:
        1. Group entries by date
        2. For each date:
           a) Calculate totals for info
           b) ALWAYS find pairs by transaction amounts
           c) If amount appears 3+ times → mark as "suspicious"
           d) Unpaired entries = discrepancies (even if day totals match!)
        """
        entries1 = self.parse_act(self.our_act_content, self.our_act_settings)
        entries2 = self.parse_act(self.counterparty_act_content, self.counterparty_act_settings)

        # Handle empty cases
        if not entries1 and not entries2:
            return {
                'status': 'completed',
                'total_records': 0,
                'matched': 0,
                'mismatched': 0,
                'not_found_in_source1': 0,
                'not_found_in_source2': 0,
                'data': [],
                'day_summaries': [],
                'summary': {
                    'total_entries_act1': 0,
                    'total_entries_act2': 0,
                    'matched_count': 0,
                    'match_rate': 0,
                    'has_discrepancies': False
                }
            }

        # 1. Group by date
        by_date1: Dict[str, List[ActEntry]] = defaultdict(list)
        by_date2: Dict[str, List[ActEntry]] = defaultdict(list)

        for e in entries1:
            by_date1[e.date].append(e)
        for e in entries2:
            by_date2[e.date].append(e)

        all_dates = set(by_date1.keys()) | set(by_date2.keys())
        results = []
        day_summaries = []

        for date in sorted(all_dates):
            our_entries = by_date1.get(date, [])
            cp_entries = by_date2.get(date, [])

            # 2. Calculate day totals (for information)
            our_debit_total = sum(e.debit for e in our_entries)
            our_credit_total = sum(e.credit for e in our_entries)
            cp_debit_total = sum(e.debit for e in cp_entries)
            cp_credit_total = sum(e.credit for e in cp_entries)

            # Check if day totals match (mirror: our debit = cp credit, our credit = cp debit)
            day_totals_match = (
                abs(our_debit_total - cp_credit_total) < 0.01 and
                abs(our_credit_total - cp_debit_total) < 0.01
            )

            # Save day summary
            day_summaries.append({
                'date': date,
                'our_debit': our_debit_total,
                'our_credit': our_credit_total,
                'cp_debit': cp_debit_total,
                'cp_credit': cp_credit_total,
                'debit_diff': round(our_debit_total - cp_credit_total, 2),
                'credit_diff': round(our_credit_total - cp_debit_total, 2),
                'matches': day_totals_match
            })

            # 3. Three-phase matching (even if totals match)
            our_amounts = [(e.amount, e) for e in our_entries]
            cp_amounts = [(e.amount, e) for e in cp_entries]

            matched_our: set = set()
            matched_cp: set = set()

            def _make_matched_row(e1: ActEntry, e2: ActEntry, phase: str) -> dict:
                return {
                    'date': e1.date,
                    'document': e1.document,
                    'our_doc_number': e1.doc_number,
                    'our_debit': e1.debit,
                    'our_credit': e1.credit,
                    'cp_debit': e2.debit,
                    'cp_credit': e2.credit,
                    'cp_document': e2.document,
                    'cp_doc_number': e2.doc_number,
                    'debit_diff': 0,
                    'credit_diff': 0,
                    'match_phase': phase,
                    'status': 'Совпадает'
                }

            def _numbers_match(e1: ActEntry, e2: ActEntry) -> bool:
                """Check if doc numbers match: direct or via extra_number"""
                if not e1.doc_number or not e2.doc_number:
                    return False
                # Direct match
                if e1.doc_number == e2.doc_number:
                    return True
                # Cross-match: our extra_number == cp doc_number
                if e1.extra_number and e1.extra_number == e2.doc_number:
                    return True
                # Cross-match: cp extra_number == our doc_number
                if e2.extra_number and e2.extra_number == e1.doc_number:
                    return True
                return False

            # Phase 1: strict match by (amount + doc_number)
            for i, (amt1, e1) in enumerate(our_amounts):
                if i in matched_our:
                    continue
                for j, (amt2, e2) in enumerate(cp_amounts):
                    if j in matched_cp:
                        continue
                    if abs(amt1 - amt2) < 0.01 and _numbers_match(e1, e2):
                        matched_our.add(i)
                        matched_cp.add(j)
                        results.append(_make_matched_row(e1, e2, 'Фаза 1: номер + сумма'))
                        break

            # Phase 2: match by (amount + op_type)
            for i, (amt1, e1) in enumerate(our_amounts):
                if i in matched_our:
                    continue
                for j, (amt2, e2) in enumerate(cp_amounts):
                    if j in matched_cp:
                        continue
                    if abs(amt1 - amt2) < 0.01 and e1.op_type == e2.op_type:
                        matched_our.add(i)
                        matched_cp.add(j)
                        results.append(_make_matched_row(e1, e2, 'Фаза 2: тип + сумма'))
                        break

            # Phase 3: match by amount only
            for i, (amt1, e1) in enumerate(our_amounts):
                if i in matched_our:
                    continue
                for j, (amt2, e2) in enumerate(cp_amounts):
                    if j in matched_cp:
                        continue
                    if abs(amt1 - amt2) < 0.01:
                        matched_our.add(i)
                        matched_cp.add(j)
                        results.append(_make_matched_row(e1, e2, 'Фаза 3: только сумма'))
                        break

            # Unpaired from our side = discrepancy
            for i, (amt, e) in enumerate(our_amounts):
                if i not in matched_our:
                    results.append({
                        'date': e.date,
                        'document': e.document,
                        'our_doc_number': e.doc_number,
                        'our_debit': e.debit,
                        'our_credit': e.credit,
                        'cp_debit': None,
                        'cp_credit': None,
                        'cp_document': None,
                        'cp_doc_number': None,
                        'debit_diff': e.debit,
                        'credit_diff': e.credit,
                        'match_phase': None,
                        'status': 'Не найдено у контрагента'
                    })

            # Unpaired from counterparty side = discrepancy
            for j, (amt, e) in enumerate(cp_amounts):
                if j not in matched_cp:
                    results.append({
                        'date': e.date,
                        'document': e.document,
                        'our_doc_number': None,
                        'our_debit': None,
                        'our_credit': None,
                        'cp_debit': e.debit,
                        'cp_credit': e.credit,
                        'cp_document': e.document,
                        'cp_doc_number': e.doc_number,
                        'debit_diff': -e.credit,
                        'credit_diff': -e.debit,
                        'match_phase': None,
                        'status': 'Не найдено у нас'
                    })

        # Statistics
        matched = sum(1 for r in results if r['status'] == 'Совпадает')
        not_found_cp = sum(1 for r in results if r['status'] == 'Не найдено у контрагента')
        not_found_our = sum(1 for r in results if r['status'] == 'Не найдено у нас')

        return {
            'status': 'completed',
            'total_records': len(results),
            'matched': matched,
            'mismatched': 0,
            'not_found_in_source1': not_found_cp,
            'not_found_in_source2': not_found_our,
            'data': results,
            'day_summaries': day_summaries,
            'summary': {
                'total_entries_act1': len(entries1),
                'total_entries_act2': len(entries2),
                'matched_count': matched,
                'match_rate': round(matched / max(len(entries1), len(entries2)) * 100, 1) if entries1 or entries2 else 0,
                'has_discrepancies': not_found_cp > 0 or not_found_our > 0
            }
        }
