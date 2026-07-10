from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ColumnMapping(BaseModel):
    source_column: int
    target_field: str


class ParserSettings(BaseModel):
    header_row: int = 0
    column_mappings: Dict[str, int] = {}
    doc_filter: Optional[str] = None
    date_extract_from_text: bool = False
    date_format: Optional[str] = None  # 'DD.MM.YYYY' or 'DD.MM.YY'
    date_source_column: Optional[int] = None


class PreviewRequest(BaseModel):
    session_id: str
    file_key: str
    header_row: int = 0
    num_rows: int = 10


class PreviewResponse(BaseModel):
    columns: List[str]
    data: List[List[Any]]
    total_rows: int


class Case1Settings(BaseModel):
    session_id: str
    account_6010: ParserSettings
    esf_report: ParserSettings


class Case3Settings(BaseModel):
    session_id: str
    account_3310: ParserSettings
    esf_report: ParserSettings


class Case2Settings(BaseModel):
    session_id: str
    our_act: ParserSettings
    counterparty_act: ParserSettings


class ReconciliationResult(BaseModel):
    status: str
    total_records: int
    matched: int
    mismatched: int
    not_found_in_source1: int
    not_found_in_source2: int
    data: List[Dict[str, Any]]


class UploadResponse(BaseModel):
    session_id: str
    files: Dict[str, str]
    message: str
