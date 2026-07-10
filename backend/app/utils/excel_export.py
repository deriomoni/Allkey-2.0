import pandas as pd
from io import BytesIO
from typing import Dict, List, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows


class ExcelExporter:
    """Export reconciliation results to Excel with formatting"""

    COLORS = {
        'header': 'CCE5FF',
        'matched': 'C6EFCE',
        'mismatched': 'FFC7CE',
        'not_found': 'FFEB9C',
    }

    def __init__(self, results: Dict[str, Any], case_type: str):
        self.results = results
        self.case_type = case_type

    def export(self) -> bytes:
        """Export results to Excel file"""
        wb = Workbook()

        if self.case_type == 'case2' and 'day_summaries' in self.results:
            # Case 2: Two sheets - day summaries first, then transactions
            ws_days = wb.active
            ws_days.title = "Итоги по дням"
            self._add_day_summaries(ws_days)
            self._adjust_columns(ws_days)

            ws_trans = wb.create_sheet("Транзакции")
            self._add_summary(ws_trans)
            self._add_data(ws_trans)
            self._adjust_columns(ws_trans)
        else:
            # Case 1 or fallback: single sheet
            ws = wb.active
            ws.title = "Результаты сверки"
            self._add_summary(ws)
            self._add_data(ws)
            self._adjust_columns(ws)

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    def _add_day_summaries(self, ws):
        """Add day summaries sheet for Case 2"""
        day_summaries = self.results.get('day_summaries', [])

        # Title
        ws['A1'] = "Итоги по дням"
        ws['A1'].font = Font(bold=True, size=14)

        # Headers
        headers = ['Дата', 'Наш дебет', 'Наш кредит', 'Дебет контрагента', 'Кредит контрагента', 'Разница дебет', 'Разница кредит', 'Статус']
        header_fill = PatternFill(start_color=self.COLORS['header'], fill_type="solid")
        header_font = Font(bold=True)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        start_row = 3
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center')

        # Data rows
        for row_idx, day in enumerate(day_summaries, start_row + 1):
            status = "✓ Совпадает" if day['matches'] else "✗ Расхождение"
            row_data = [
                day['date'],
                day['our_debit'],
                day['our_credit'],
                day['cp_debit'],
                day['cp_credit'],
                day['debit_diff'],
                day['credit_diff'],
                status
            ]

            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border

                # Color based on match status
                if day['matches']:
                    cell.fill = PatternFill(start_color=self.COLORS['matched'], fill_type="solid")
                else:
                    cell.fill = PatternFill(start_color=self.COLORS['mismatched'], fill_type="solid")

        # Add totals row
        if day_summaries:
            total_row = len(day_summaries) + start_row + 1
            ws.cell(row=total_row, column=1, value="ИТОГО").font = Font(bold=True)
            ws.cell(row=total_row, column=2, value=sum(d['our_debit'] for d in day_summaries)).font = Font(bold=True)
            ws.cell(row=total_row, column=3, value=sum(d['our_credit'] for d in day_summaries)).font = Font(bold=True)
            ws.cell(row=total_row, column=4, value=sum(d['cp_debit'] for d in day_summaries)).font = Font(bold=True)
            ws.cell(row=total_row, column=5, value=sum(d['cp_credit'] for d in day_summaries)).font = Font(bold=True)
            ws.cell(row=total_row, column=6, value=sum(d['debit_diff'] for d in day_summaries)).font = Font(bold=True)
            ws.cell(row=total_row, column=7, value=sum(d['credit_diff'] for d in day_summaries)).font = Font(bold=True)

            for col_idx in range(1, 8):
                ws.cell(row=total_row, column=col_idx).border = border

    def _add_summary(self, ws):
        """Add summary section at the top"""
        summary_data = [
            ["Результаты сверки"],
            [""],
            ["Всего записей:", self.results['total_records']],
            ["Совпадает:", self.results['matched']],
            ["Расхождения:", self.results['mismatched']],
            ["Не найдено в источнике 1:", self.results['not_found_in_source1']],
            ["Не найдено в источнике 2:", self.results['not_found_in_source2']],
            [""],
        ]

        header_font = Font(bold=True, size=14)
        ws['A1'].font = header_font

        for row_idx, row_data in enumerate(summary_data, 1):
            for col_idx, value in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)

    def _add_data(self, ws):
        """Add reconciliation data"""
        data = self.results['data']
        if not data:
            return

        start_row = 9
        df = pd.DataFrame(data)

        # Column headers
        if self.case_type == 'case1':
            columns = {
                'date': 'Дата',
                'document': 'Документ',
                'counterparty_6010': 'Контрагент (6010)',
                'recipient_esf': 'Получатель (ЭСФ)',
                'amount_6010': 'Сумма 6010',
                'amount_esf': 'Сумма ЭСФ',
                'esf_number': '№ ЭСФ',
                'esf_reg_number': 'Рег. номер ЭСФ',
                'difference': 'Разница',
                'status': 'Статус'
            }
        elif self.case_type == 'case3':
            columns = {
                'date': 'Дата',
                'document': 'Документ',
                'tru': 'ТРУ',
                'sender_esf': 'Отправитель (ЭСФ)',
                'recipient_esf': 'Получатель (ЭСФ)',
                'amount_3310': 'Сумма 3310',
                'amount_esf': 'Сумма ЭСФ',
                'esf_number': '№ ЭСФ',
                'esf_reg_number': 'Рег. номер ЭСФ',
                'difference': 'Разница',
                'status': 'Статус'
            }
        else:  # case2
            columns = {
                'date': 'Дата',
                'document': 'Наш документ',
                'our_doc_number': '№ нашего док.',
                'cp_document': 'Документ контрагента',
                'cp_doc_number': '№ док. контрагента',
                'our_debit': 'Наш дебет',
                'our_credit': 'Наш кредит',
                'cp_debit': 'Дебет контрагента',
                'cp_credit': 'Кредит контрагента',
                'debit_diff': 'Разница дебет',
                'credit_diff': 'Разница кредит',
                'match_phase': 'Метод сопоставления',
                'status': 'Статус'
            }

        # Write headers
        header_fill = PatternFill(start_color=self.COLORS['header'], fill_type="solid")
        header_font = Font(bold=True)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        for col_idx, (key, header) in enumerate(columns.items(), 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center')

        # Write data rows
        for row_idx, record in enumerate(data, start_row + 1):
            for col_idx, key in enumerate(columns.keys(), 1):
                value = record.get(key)
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border

                # Color based on status
                status = record.get('status', '')
                if status == 'Совпадает':
                    cell.fill = PatternFill(start_color=self.COLORS['matched'], fill_type="solid")
                elif status == 'Расхождение':
                    cell.fill = PatternFill(start_color=self.COLORS['mismatched'], fill_type="solid")
                elif 'Не найдено' in status:
                    cell.fill = PatternFill(start_color=self.COLORS['not_found'], fill_type="solid")

    def _adjust_columns(self, ws):
        """Auto-adjust column widths"""
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
