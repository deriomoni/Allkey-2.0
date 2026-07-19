import math
from io import BytesIO
from typing import List, Any

import pandas as pd

from app.reconciliation.excel_parser import ExcelParseError, _canonicalize_xlsx


def _engine_for(content: bytes) -> str:
    if len(content) < 4:
        raise ExcelParseError("Файл слишком маленький или пустой")
    if content[:2] == b"PK":
        return "openpyxl"
    if content[:2] == b"\xd0\xcf":
        return "xlrd"
    raise ExcelParseError("Неподдерживаемый формат файла (нужен .xlsx или .xls)")


def read_aoa(content: bytes) -> List[List[Any]]:
    """Первый лист книги -> «сырая» матрица ячеек (список строк).

    Повторяет определение движка и фикс регистра OOXML-частей из ExcelParser.
    Пустые ячейки -> None, даты -> datetime, числа -> int/float, текст -> str.
    Именно это ожидают перенесённые движки сверки.
    """
    engine = _engine_for(content)
    try:
        df = pd.read_excel(BytesIO(content), header=None, engine=engine)
    except Exception:
        if engine == "openpyxl":
            fixed = _canonicalize_xlsx(content)
            if fixed is not None:
                df = pd.read_excel(BytesIO(fixed), header=None, engine="openpyxl")
            else:
                raise ExcelParseError("Ошибка чтения Excel файла")
        else:
            raise ExcelParseError("Ошибка чтения Excel файла")

    out: List[List[Any]] = []
    for row in df.values.tolist():
        cells = []
        for v in row:
            if isinstance(v, float) and math.isnan(v):
                cells.append(None)
            else:
                cells.append(v)
        out.append(cells)
    return out
