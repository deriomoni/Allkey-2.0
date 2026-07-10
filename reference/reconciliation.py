"""
Ядро сверки бухгалтерских документов
Reconciliation Engine
"""

import pandas as pd
import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Transaction6010:
    """Транзакция из карточки счета 6010"""
    date: str
    doc_number: str
    doc_date: str
    counterparty: str
    contract: Optional[str]
    amount: float
    raw_doc: str
    
    def to_dict(self):
        return asdict(self)


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
    
    def to_dict(self):
        return asdict(self)


class ReconciliationEngine:
    """
    Движок сверки документов
    
    Поддерживает:
    - Карточка счета 6010 из 1С
    - Реестр ЭСФ из ИС ЭСФ
    """
    
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance
        self.date_pattern = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
    
    def reconcile(self, path_1c: str, path_esf: str) -> dict:
        """
        Основной метод сверки
        
        Args:
            path_1c: путь к файлу карточки счета 6010
            path_esf: путь к файлу реестра ЭСФ
            
        Returns:
            Результат сверки с расхождениями
        """
        # Парсим оба файла
        transactions = self.parse_1c(path_1c)
        invoices = self.parse_esf(path_esf)
        
        # Группируем транзакции 1С по документам
        grouped = self.group_transactions(transactions)
        
        # Сравниваем
        result = self.compare(grouped, invoices)
        
        # Добавляем мета-информацию
        result['meta'] = {
            'total_1c_transactions': len(transactions),
            'total_1c_documents': len(grouped),
            'total_esf_invoices': len(invoices)
        }
        
        return result
    
    def parse_1c(self, filepath: str) -> list[Transaction6010]:
        """Парсит карточку счета 6010 из 1С"""
        
        df = pd.read_excel(filepath, header=None)
        transactions = []
        
        for idx, row in df.iterrows():
            cell_0 = str(row[0]).strip() if pd.notna(row[0]) else ''
            
            # Пропускаем не-даты
            if not self.date_pattern.match(cell_0):
                continue
            
            # Проверяем что это реализация
            cell_1 = str(row[1]) if pd.notna(row[1]) else ''
            if 'Реализация' not in cell_1:
                continue
            
            try:
                doc_info = self._parse_document_cell(cell_1)
                cell_3 = str(row[3]) if pd.notna(row[3]) else ''
                counterparty_info = self._parse_counterparty_cell(cell_3)
                amount = float(row[9]) if pd.notna(row[9]) else 0.0
                
                tx = Transaction6010(
                    date=cell_0,
                    doc_number=doc_info.get('number', ''),
                    doc_date=doc_info.get('date', ''),
                    counterparty=counterparty_info.get('name', ''),
                    contract=counterparty_info.get('contract'),
                    amount=amount,
                    raw_doc=cell_1[:100]
                )
                transactions.append(tx)
                
            except Exception:
                continue
        
        return transactions
    
    def parse_esf(self, filepath: str) -> list[InvoiceESF]:
        """Парсит реестр счетов-фактур из ИС ЭСФ"""
        
        df = pd.read_excel(filepath, header=0)
        
        # Переименовываем колонки
        df.columns = [
            'sender_bin', 'sender_name', 'receiver_bin', 'receiver_name',
            'status', 'invoice_number', 'esf_reg_number', 'issue_date',
            'operation_date', 'change_date', 'cancel_reason',
            'amount_with_vat', 'vat_amount', 'excise_amount', 'amount_without_vat',
            'turnover_amount', 'supplier_status', 'bik', 'receiver_status',
            'shipper_name', 'shipper_bin', 'consignee_name', 'consignee_bin',
            'iik', 'product_code', 'payment_purpose'
        ]
        
        invoices = []
        
        for idx, row in df.iloc[1:].iterrows():
            try:
                invoice = InvoiceESF(
                    invoice_number=str(row['invoice_number']),
                    esf_reg_number=str(row['esf_reg_number']),
                    issue_date=self._format_date(row['issue_date']),
                    operation_date=self._format_date(row['operation_date']),
                    counterparty_bin=str(row['receiver_bin']) if pd.notna(row['receiver_bin']) else None,
                    counterparty_name=self._normalize_name(str(row['receiver_name'])),
                    amount_with_vat=float(row['amount_with_vat']) if pd.notna(row['amount_with_vat']) else 0,
                    vat_amount=float(row['vat_amount']) if pd.notna(row['vat_amount']) else 0,
                    amount_without_vat=float(row['amount_without_vat']) if pd.notna(row['amount_without_vat']) else 0,
                    status=str(row['status'])
                )
                invoices.append(invoice)
            except Exception:
                continue
        
        return invoices
    
    def group_transactions(self, transactions: list[Transaction6010]) -> dict:
        """Группирует транзакции по номеру документа"""
        
        grouped = {}
        
        for tx in transactions:
            key = (tx.doc_number, tx.doc_date)
            
            if key not in grouped:
                grouped[key] = {
                    'doc_number': tx.doc_number,
                    'doc_date': tx.doc_date,
                    'counterparty': tx.counterparty,
                    'contract': tx.contract,
                    'total_amount': 0,
                    'line_count': 0
                }
            
            grouped[key]['total_amount'] += tx.amount
            grouped[key]['line_count'] += 1
        
        return grouped
    
    def compare(self, grouped: dict, invoices: list[InvoiceESF]) -> dict:
        """Сравнивает документы 1С с ЭСФ"""
        
        result = {
            'matched': [],
            'only_in_1c': [],
            'only_in_esf': [],
            'amount_mismatch': [],
            'summary': {}
        }
        
        # Индекс ЭСФ по дате операции
        esf_by_date = {}
        for inv in invoices:
            date_key = inv.operation_date
            if date_key not in esf_by_date:
                esf_by_date[date_key] = []
            esf_by_date[date_key].append(inv)
        
        matched_esf_ids = set()
        
        # Сопоставляем
        for key, tx_group in grouped.items():
            doc_num, doc_date = key
            total_amount = tx_group['total_amount']
            counterparty = tx_group['counterparty']
            
            found = False
            candidates = esf_by_date.get(doc_date, [])
            
            for inv in candidates:
                if self._similar_names(counterparty, inv.counterparty_name):
                    diff = abs(total_amount - inv.amount_without_vat)
                    
                    if diff <= self.tolerance:
                        result['matched'].append({
                            '1c_doc': doc_num,
                            '1c_date': doc_date,
                            '1c_amount': round(total_amount, 2),
                            '1c_counterparty': counterparty,
                            'esf_number': inv.invoice_number,
                            'esf_reg_number': inv.esf_reg_number,
                            'esf_date': inv.issue_date,
                            'esf_amount': round(inv.amount_without_vat, 2),
                            'esf_counterparty': inv.counterparty_name,
                            'status': 'matched'
                        })
                        matched_esf_ids.add(inv.esf_reg_number)
                        found = True
                        break
                    elif diff < total_amount * 0.1:
                        result['amount_mismatch'].append({
                            '1c_doc': doc_num,
                            '1c_date': doc_date,
                            '1c_amount': round(total_amount, 2),
                            '1c_counterparty': counterparty,
                            'esf_number': inv.invoice_number,
                            'esf_reg_number': inv.esf_reg_number,
                            'esf_date': inv.issue_date,
                            'esf_amount': round(inv.amount_without_vat, 2),
                            'esf_counterparty': inv.counterparty_name,
                            'difference': round(total_amount - inv.amount_without_vat, 2),
                            'difference_percent': round((total_amount - inv.amount_without_vat) / inv.amount_without_vat * 100, 2),
                            'status': 'mismatch'
                        })
                        matched_esf_ids.add(inv.esf_reg_number)
                        found = True
                        break
            
            if not found:
                result['only_in_1c'].append({
                    'doc_number': doc_num,
                    'doc_date': doc_date,
                    'amount': round(total_amount, 2),
                    'counterparty': counterparty,
                    'line_count': tx_group['line_count'],
                    'status': 'only_1c'
                })
        
        # ЭСФ без пары в 1С
        for inv in invoices:
            if inv.esf_reg_number not in matched_esf_ids:
                result['only_in_esf'].append({
                    'esf_number': inv.invoice_number,
                    'esf_reg_number': inv.esf_reg_number,
                    'issue_date': inv.issue_date,
                    'operation_date': inv.operation_date,
                    'amount_with_vat': round(inv.amount_with_vat, 2),
                    'amount_without_vat': round(inv.amount_without_vat, 2),
                    'counterparty': inv.counterparty_name,
                    'counterparty_bin': inv.counterparty_bin,
                    'invoice_status': inv.status,
                    'status': 'only_esf'
                })
        
        # Итоги
        total_1c = sum(g['total_amount'] for g in grouped.values())
        total_esf = sum(inv.amount_without_vat for inv in invoices)
        
        result['summary'] = {
            'total_1c_docs': len(grouped),
            'total_esf_docs': len(invoices),
            'matched_count': len(result['matched']),
            'only_in_1c_count': len(result['only_in_1c']),
            'only_in_esf_count': len(result['only_in_esf']),
            'amount_mismatch_count': len(result['amount_mismatch']),
            'total_1c_amount': round(total_1c, 2),
            'total_esf_amount': round(total_esf, 2),
            'total_difference': round(total_1c - total_esf, 2),
            'has_discrepancies': (
                len(result['only_in_1c']) > 0 or 
                len(result['only_in_esf']) > 0 or 
                len(result['amount_mismatch']) > 0
            )
        }
        
        return result
    
    def _parse_document_cell(self, text: str) -> dict:
        """Парсит ячейку документа"""
        result = {'number': '', 'date': ''}
        pattern = r'(\d{8,12})\s+от\s+(\d{2}\.\d{2}\.\d{4})'
        match = re.search(pattern, text)
        if match:
            result['number'] = match.group(1).lstrip('0') or '0'
            result['date'] = match.group(2)
        return result
    
    def _parse_counterparty_cell(self, text: str) -> dict:
        """Парсит ячейку контрагента"""
        result = {'name': '', 'contract': None}
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or 'Головное подразделение' in line or '<...>' in line:
                continue
            if 'Договор' in line:
                result['contract'] = line
                continue
            if not result['name']:
                result['name'] = self._normalize_name(line)
        
        return result
    
    def _normalize_name(self, name: str) -> str:
        """Нормализует название контрагента"""
        name = name.lower().strip()
        name = re.sub(r'[«»""\'"]', '', name)
        patterns = [r'\bтоо\b', r'\bооо\b', r'\bао\b', r'\bпао\b', r'\bзао\b',
                    r'\bсп\b', r'\bллп\b', r'\bllp\b', r'\bltd\b',
                    r'\bтоварищество с ограниченной ответственностью\b']
        for p in patterns:
            name = re.sub(p, '', name, flags=re.IGNORECASE)
        return ' '.join(name.split())
    
    def _format_date(self, value) -> str:
        """Форматирует дату"""
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
        """Проверяет похожесть названий"""
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
