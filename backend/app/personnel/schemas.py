"""Pydantic schemas for the personnel module.

This tranche exposes only the foundation endpoints (rates + ИИН/БИН checks);
Company/Employee/Employment CRUD schemas are added with the form in a later step.
"""
from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class IinCheckRequest(BaseModel):
    iin: str
    birth_date: Optional[date] = None   # optional cross-check from the form
    gender: Optional[str] = None        # "male" | "female"


class IinCheckResponse(BaseModel):
    valid: bool
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    warnings: List[str] = []


class BinCheckRequest(BaseModel):
    bin: str


class BinCheckResponse(BaseModel):
    valid: bool


class RatesResponse(BaseModel):
    effective_from: date
    effective_to: Optional[date] = None
    mrp: int
    mzp: int
    ipn_rate: float
    base_deduction_mrp: int
    opv_rate: float
    opvr_rate: float
    so_rate: float
    vosms_rate: float
    oosms_rate: float
    sn_rate: float
    unified_payment_rate: float
