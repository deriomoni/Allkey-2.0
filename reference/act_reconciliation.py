"""
Кейс 2: Сверка двух актов сверки взаиморасчетов
Reconciliation of two reconciliation acts between counterparties
"""

import pandas as pd
import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ActEntry:
    """Запись из акта сверки"""
    date: str
    document: str
    debit: float
    credit: float
    amount: float  # abs value
    op_type: str   # 'товар', 'оплата', 'прочее'
    row_index: int
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ActMetadata:
    """Метаданные акта сверки"""
    company_name: str
    counterparty_name: str
    period_start: str
    period_end: str
    opening_balance: float
    closing_balance: float
    total_debit: float
    total_credit: float


class ActReconciliationEngine:
    """
    Движок сверки актов сверки взаиморасчетов
    
    Особенности:
    - Два акта от разных сторон (покупатель/продавец)
    - Дебет/Кредит зеркальные
    - Сопоставление по: дата + сумма + тип операции
    - Номера документов могут отличаться (внутренние номера разные)
    """
    
    def __init__(self):
        self.date_pattern = re.compile(r'^\d{2}\.\d{2}\.\d{2}$')
    
    def reconcile(self, path_act1: str, path_act2: str) -> dict:
        """
        Сравнивает два акта сверки
        
        Args:
            path_act1: путь к первому акту
            path_act2: путь к второму акту
            
        Returns:
            Результат сверки
        """
        # Парсим оба акта
        entries1, meta1 = self.parse_act(path_act1)
        entries2, meta2 = self.parse_act(path_act2)
        
        # Сверяем
        result = self.compare_acts(entries1, entries2)
        
        # Добавляем метаданные
        result['act1'] = {
            'filename': path_act1,
            'company': meta1.company_name if meta1 else 'Unknown',
            'entries_count': len(entries1),
            'total_debit': round(sum(e.debit for e in entries1), 2),
            'total_credit': round(sum(e.credit for e in entries1), 2),
            'opening_balance': meta1.opening_balance if meta1 else 0,
        }
        result['act2'] = {
            'filename': path_act2,
            'company': meta2.company_name if meta2 else 'Unknown',
            'entries_count': len(entries2),
            'total_debit': round(sum(e.debit for e in entries2), 2),
            'total_credit': round(sum(e.credit for e in entries2), 2),
            'opening_balance': meta2.opening_balance if meta2 else 0,
        }
        
        return result
    
    def parse_act(self, filepath: str) -> tuple[list[ActEntry], Optional[ActMetadata]]:
        """
        Парсит акт сверки взаиморасчетов
        
        Структура файла:
        - Row 1: заголовок "Акт сверки"
        - Row 2: период и контрагенты
        - Row 7: заголовки таблицы (Дата, Документ, Дебет, Кредит)
        - Row 8: сальдо на начало
        - Row 9+: операции (дата в col[1], документ в col[2], дебет в col[4], кредит в col[5])
        """
        df = pd.read_excel(filepath, header=None)
        
        entries = []
        metadata = self._extract_metadata(df)
        
        for idx, row in df.iterrows():
            cell_1 = str(row[1]).strip() if pd.notna(row[1]) else ''
            
            # Ищем строки с датой операции (формат DD.MM.YY)
            if not self.date_pattern.match(cell_1):
                continue
            
            date = cell_1
            doc = str(row[2]) if pd.notna(row[2]) else ''
            
            # Пропускаем строки со счетами-фактурами (они дублируют инфу)
            if 'счет-фактура' in doc.lower():
                continue
            
            debit = float(row[4]) if pd.notna(row[4]) else 0
            credit = float(row[5]) if pd.notna(row[5]) else 0
            amount = debit if debit > 0 else credit
            
            # Определяем тип операции
            op_type = self._determine_op_type(doc)
            
            entry = ActEntry(
                date=date,
                document=doc,
                debit=debit,
                credit=credit,
                amount=amount,
                op_type=op_type,
                row_index=idx
            )
            entries.append(entry)
        
        return entries, metadata
    
    def _extract_metadata(self, df: pd.DataFrame) -> Optional[ActMetadata]:
        """Извлекает метаданные из заголовка акта"""
        try:
            # Ищем название компании и период в первых строках
            company_name = ''
            counterparty_name = ''
            opening_balance = 0
            
            for idx, row in df.head(10).iterrows():
                cell = str(row[1]) if pd.notna(row[1]) else ''
                
                # Ищем сальдо на начало
                if 'Сальдо на начало' in cell:
                    # Сальдо в колонке 4 (дебет) или 5 (кредит)
                    if pd.notna(row[4]):
                        opening_balance = float(row[4])
                    elif pd.notna(row[5]):
                        opening_balance = -float(row[5])  # Кредитовое сальдо
                    break
                
                # Ищем "По данным ..." для названия компании
                if 'По данным' in cell:
                    match = re.search(r'По данным\s+(.+?),?\s*KZT', cell)
                    if match:
                        company_name = match.group(1).strip()
            
            return ActMetadata(
                company_name=company_name,
                counterparty_name=counterparty_name,
                period_start='',
                period_end='',
                opening_balance=opening_balance,
                closing_balance=0,
                total_debit=0,
                total_credit=0
            )
        except Exception:
            return None
    
    def _determine_op_type(self, doc: str) -> str:
        """Определяет тип операции по тексту документа"""
        doc_lower = doc.lower()
        
        if 'поступление' in doc_lower or 'реализация' in doc_lower:
            return 'товар'
        elif 'платежное' in doc_lower or 'оплата' in doc_lower:
            return 'оплата'
        elif 'корректировка' in doc_lower:
            return 'корректировка'
        elif 'возврат' in doc_lower:
            return 'возврат'
        else:
            return 'прочее'
    
    def compare_acts(self, entries1: list[ActEntry], entries2: list[ActEntry]) -> dict:
        """
        Сравнивает записи двух актов
        
        Логика сопоставления:
        - По дате + сумме + типу операции
        - Дебет у одного = Кредит у другого (зеркально)
        """
        result = {
            'matched': [],
            'only_in_act1': [],
            'only_in_act2': [],
            'amount_mismatch': [],  # На будущее, если понадобится fuzzy matching
            'summary': {}
        }
        
        # Копируем списки для работы
        remaining2 = list(entries2)
        
        for e1 in entries1:
            key1 = (e1.date, e1.amount, e1.op_type)
            found = False
            
            for i, e2 in enumerate(remaining2):
                key2 = (e2.date, e2.amount, e2.op_type)
                
                if key1 == key2:
                    # Проверяем зеркальность дебет/кредит
                    is_mirror = (
                        (e1.debit > 0 and e2.credit > 0 and abs(e1.debit - e2.credit) < 0.01) or
                        (e1.credit > 0 and e2.debit > 0 and abs(e1.credit - e2.debit) < 0.01)
                    )
                    
                    result['matched'].append({
                        'date': e1.date,
                        'amount': e1.amount,
                        'op_type': e1.op_type,
                        'act1_doc': e1.document,
                        'act1_debit': e1.debit,
                        'act1_credit': e1.credit,
                        'act2_doc': e2.document,
                        'act2_debit': e2.debit,
                        'act2_credit': e2.credit,
                        'is_mirror': is_mirror,
                        'status': 'matched'
                    })
                    remaining2.pop(i)
                    found = True
                    break
            
            if not found:
                result['only_in_act1'].append({
                    'date': e1.date,
                    'document': e1.document,
                    'debit': e1.debit,
                    'credit': e1.credit,
                    'amount': e1.amount,
                    'op_type': e1.op_type,
                    'status': 'only_act1'
                })
        
        # Оставшиеся записи из акта 2
        for e2 in remaining2:
            result['only_in_act2'].append({
                'date': e2.date,
                'document': e2.document,
                'debit': e2.debit,
                'credit': e2.credit,
                'amount': e2.amount,
                'op_type': e2.op_type,
                'status': 'only_act2'
            })
        
        # Считаем итоги
        total_matched = sum(m['amount'] for m in result['matched'])
        total_only1 = sum(e['amount'] for e in result['only_in_act1'])
        total_only2 = sum(e['amount'] for e in result['only_in_act2'])
        
        result['summary'] = {
            'total_entries_act1': len(entries1),
            'total_entries_act2': len(entries2),
            'matched_count': len(result['matched']),
            'only_in_act1_count': len(result['only_in_act1']),
            'only_in_act2_count': len(result['only_in_act2']),
            'matched_amount': round(total_matched, 2),
            'only_in_act1_amount': round(total_only1, 2),
            'only_in_act2_amount': round(total_only2, 2),
            'has_discrepancies': len(result['only_in_act1']) > 0 or len(result['only_in_act2']) > 0,
            'match_rate': round(len(result['matched']) / max(len(entries1), len(entries2)) * 100, 1) if entries1 or entries2 else 0
        }
        
        return result


# CLI для тестирования
if __name__ == '__main__':
    import json
    import sys
    
    engine = ActReconciliationEngine()
    
    # Тест с файлами
    path1 = '/mnt/user-data/uploads/Анвар_1_кв_2025.xlsx'
    path2 = '/mnt/user-data/uploads/АП_1_2025.xls'
    
    result = engine.reconcile(path1, path2)
    
    print("=" * 60)
    print("СВЕРКА АКТОВ ВЗАИМОРАСЧЕТОВ")
    print("=" * 60)
    print(f"\nАкт 1: {result['act1']['company']}")
    print(f"  Записей: {result['act1']['entries_count']}")
    print(f"  Дебет: {result['act1']['total_debit']:,.2f}")
    print(f"  Кредит: {result['act1']['total_credit']:,.2f}")
    
    print(f"\nАкт 2: {result['act2']['company']}")
    print(f"  Записей: {result['act2']['entries_count']}")
    print(f"  Дебет: {result['act2']['total_debit']:,.2f}")
    print(f"  Кредит: {result['act2']['total_credit']:,.2f}")
    
    print(f"\n--- Результат сверки ---")
    print(f"Совпало записей: {result['summary']['matched_count']}")
    print(f"Только в акте 1: {result['summary']['only_in_act1_count']}")
    print(f"Только в акте 2: {result['summary']['only_in_act2_count']}")
    print(f"Процент совпадения: {result['summary']['match_rate']}%")
    
    if result['summary']['has_discrepancies']:
        print("\n⚠️  ЕСТЬ РАСХОЖДЕНИЯ!")
        
        if result['only_in_act1']:
            print("\nТолько в акте 1:")
            for e in result['only_in_act1'][:5]:
                print(f"  {e['date']} | {e['amount']:,.2f} | {e['document'][:50]}")
        
        if result['only_in_act2']:
            print("\nТолько в акте 2:")
            for e in result['only_in_act2'][:5]:
                print(f"  {e['date']} | {e['amount']:,.2f} | {e['document'][:50]}")
    else:
        print("\n✅ Все записи совпали!")
    
    # Сохраняем JSON
    with open('/home/claude/act_comparison_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nРезультат сохранен в act_comparison_result.json")
