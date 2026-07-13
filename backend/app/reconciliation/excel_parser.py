import pandas as pd
import re
import zipfile
from typing import List, Dict, Any, Tuple, Optional
from io import BytesIO


class ExcelParseError(Exception):
    """Custom exception for Excel parsing errors"""
    pass


def _canonicalize_xlsx(content: bytes) -> Optional[bytes]:
    """Rebuild an .xlsx archive with canonical (lowercase) OOXML part names.

    Some 1C/counterparty exports name parts with the wrong case
    (``xl/SharedStrings.xml``), which openpyxl cannot find on a case-sensitive
    filesystem (the Linux server) — it fails with "There is no item named
    'xl/sharedStrings.xml'". Returns rebuilt bytes, or None if it isn't a zip.
    """
    canon = {
        "xl/sharedstrings.xml": "xl/sharedStrings.xml",
        "xl/styles.xml": "xl/styles.xml",
        "xl/workbook.xml": "xl/workbook.xml",
    }
    try:
        src = BytesIO(content)
        out = BytesIO()
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                zout.writestr(canon.get(name.lower(), name), zin.read(name))
        return out.getvalue()
    except Exception:
        return None


class ExcelParser:
    def __init__(self, file_content: bytes, header_row: int = 0):
        self.file_content = file_content
        self.header_row = header_row
        self._df: Optional[pd.DataFrame] = None

    def _detect_engine(self) -> str:
        """
        Detect the appropriate pandas engine based on file magic bytes.
        - .xlsx files start with PK (ZIP format) -> use openpyxl
        - .xls files start with \xd0\xcf (OLE2) -> use xlrd
        """
        if len(self.file_content) < 4:
            raise ExcelParseError("Файл слишком маленький или пустой")

        # Check for ZIP format (xlsx)
        if self.file_content[:2] == b'PK':
            return 'openpyxl'

        # Check for OLE2 format (xls)
        if self.file_content[:2] == b'\xd0\xcf':
            return 'xlrd'

        # Try to detect by attempting openpyxl first (most common)
        raise ExcelParseError(
            "Неподдерживаемый формат файла. Поддерживаются только файлы Excel (.xlsx, .xls)"
        )

    def _read_excel_raw(self, header) -> pd.DataFrame:
        """Read the workbook with the detected engine.

        For .xlsx, retry once with canonicalized part names if openpyxl fails
        (handles archives that use ``xl/SharedStrings.xml`` with wrong case).
        """
        engine = self._detect_engine()
        try:
            return pd.read_excel(BytesIO(self.file_content), header=header, engine=engine)
        except Exception as e:
            if engine == 'openpyxl':
                fixed = _canonicalize_xlsx(self.file_content)
                if fixed is not None:
                    try:
                        return pd.read_excel(BytesIO(fixed), header=header, engine='openpyxl')
                    except Exception:
                        pass
            raise ExcelParseError(f"Ошибка чтения Excel файла: {str(e)}")

    def read(self) -> pd.DataFrame:
        if self._df is None:
            self._df = self._read_excel_raw(header=self.header_row)
        return self._df

    def read_raw(self, num_rows: Optional[int] = None) -> pd.DataFrame:
        """Read Excel without header, for preview purposes"""
        df = self._read_excel_raw(header=None)
        if num_rows:
            return df.head(num_rows)
        return df

    def get_preview(self, header_row: int = 0, num_rows: int = 10) -> Dict[str, Any]:
        """Get preview of data with specified header row"""
        df_raw = self._read_excel_raw(header=None)

        total_rows = len(df_raw)

        if header_row >= len(df_raw):
            return {
                "columns": [],
                "data": [],
                "total_rows": total_rows
            }

        columns = [str(c) for c in df_raw.iloc[header_row].tolist()]
        data_start = header_row + 1
        data_end = min(data_start + num_rows, len(df_raw))

        data = df_raw.iloc[data_start:data_end].fillna("").values.tolist()

        return {
            "columns": columns,
            "data": data,
            "total_rows": total_rows - header_row - 1
        }

    def get_column(self, col_index: int) -> pd.Series:
        df = self.read()
        return df.iloc[:, col_index]

    @staticmethod
    def parse_document_string(doc_string: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse document string like 'Реализация товаров 123 от 01.01.2024'
        Returns: (doc_type, doc_number, doc_date)
        """
        if pd.isna(doc_string) or not doc_string:
            return None, None, None

        pattern = r'(.+?)\s+(\d+)\s+от\s+(\d{2}\.\d{2}\.\d{4})'
        match = re.match(pattern, str(doc_string).strip())

        if match:
            return match.group(1).strip(), match.group(2), match.group(3)
        return None, None, None

    @staticmethod
    def normalize_date(date_val: Any) -> Optional[str]:
        """Normalize date to DD.MM.YYYY format"""
        if pd.isna(date_val):
            return None

        if isinstance(date_val, str):
            # Try to parse DD.MM.YYYY
            pattern = r'(\d{2})\.(\d{2})\.(\d{4})'
            match = re.match(pattern, date_val.strip())
            if match:
                return date_val.strip()

        try:
            dt = pd.to_datetime(date_val)
            return dt.strftime('%d.%m.%Y')
        except:
            return str(date_val)

    @staticmethod
    def normalize_amount(amount_val: Any) -> float:
        """Normalize amount to float"""
        if pd.isna(amount_val):
            return 0.0

        if isinstance(amount_val, (int, float)):
            return float(amount_val)

        try:
            # Remove spaces and replace comma with dot
            cleaned = str(amount_val).replace(' ', '').replace(',', '.')
            return float(cleaned)
        except:
            return 0.0
