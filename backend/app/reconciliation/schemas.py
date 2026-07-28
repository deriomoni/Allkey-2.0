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
    # Optional, additive fields. Case 2 (act reconciliation) populates these;
    # case 1/3 leave them unset. Declared so they survive response_model
    # filtering and reach the frontend without breaking the other cases.
    summary: Optional[Dict[str, Any]] = None
    out_of_period: Optional[List[Dict[str, Any]]] = None
    header_summary: Optional[Dict[str, Any]] = None
    common_period: Optional[str] = None
    period_mismatch: Optional[bool] = None


class UploadResponse(BaseModel):
    session_id: str
    files: Dict[str, str]
    message: str


# --- Currency / Bank reconciliations (auto-detect, без маппинга колонок) ---

class CurrencySettings(BaseModel):
    session_id: str


class BankSettings(BaseModel):
    session_id: str


class CurrencyResult(BaseModel):
    rows: List[Dict[str, Any]]
    matched: int
    off_rate: int
    no_nb: int
    no_rate: int = 0
    no_val: int = 0
    total_rows: int = 0
    total_usd: float
    total_kzt: float
    threshold: float
    balance_check: Optional[Dict[str, Any]] = None


class BankResult(BaseModel):
    rows: List[Dict[str, Any]]
    matched: int
    only_bank: int
    only_1c: int
    bank_in: float
    bank_out: float
    c1_in: float
    c1_out: float
    open_bank: Optional[float] = None
    open_c1: Optional[float] = None
    close_bank: Optional[float] = None
    close_c1: Optional[float] = None
    balance_diff: Optional[float] = None
    gaps: List[Dict[str, Any]] = []
    split_docs: List[str] = []
    currency: bool = False
    cp_mismatch: int = 0
