"""Build the nested docxtpl context from the ORM models + helpers.

The templates use nested placeholders (`{{ company.name_full }}`, not flat), so
each builder returns a plain dict namespaced by entity: company / employee /
employment / order / contract / application / hr / deductions. Every generated
string is plain text that the form surfaces as editable before rendering.

Builders read attributes off any object exposing them (SQLAlchemy models in
production, lightweight sample objects in tests) — they never touch the session.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.personnel.helpers import fio as fio_h
from app.personnel.helpers.dates import date_in_words, date_short, add_months
from app.personnel.helpers.numbers import ru_int_to_words, format_figures


# --- small utilities --------------------------------------------------------

def split_fio(full: str) -> "tuple[str, str, str]":
    """Split 'Иванов Иван Иванович' -> ('Иванов', 'Иван', 'Иванович'). Missing
    parts come back empty."""
    parts = (full or "").split()
    last = parts[0] if len(parts) > 0 else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    return last, first, middle


def _words(d: Optional[date]) -> str:
    return date_in_words(d) if d else ""


def _short(d: Optional[date]) -> str:
    return date_short(d) if d else ""


def _num(value) -> str:
    """Render a numeric column without a trailing '.0' when it is whole."""
    if value is None:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f == int(f) else str(value)


def format_id_document(employee) -> str:
    """'удостоверение личности № 012345678, выдано МВД РК 15.03.2015'."""
    kind = "удостоверение личности" if getattr(employee, "document_type", "") == "id_card" else "паспорт"
    head = kind
    if employee.document_number:
        head += f" № {employee.document_number}"
    tail = []
    if employee.document_issued_by:
        tail.append(f"выдан(о) {employee.document_issued_by}")
    if employee.document_issue_date:
        tail.append(_short(employee.document_issue_date))
    return head + (", " + " ".join(tail) if tail else "")


# --- entity contexts --------------------------------------------------------

def build_company_context(company) -> dict:
    s_last, s_first, s_middle = split_fio(company.director_fio_ru)
    s_gender = getattr(company, "director_gender", "male") or "male"
    position = company.signatory_position or "Директор"
    return {
        "name_full": company.name_ru,
        "bin": company.bin,
        "city": company.city or "",
        "address": company.legal_address or "",
        "signer_position": position,
        "signer_position_genitive": fio_h.inflect_phrase(position, fio_h.GENITIVE, s_gender),
        "signer_position_dative": fio_h.inflect_phrase(position, fio_h.DATIVE, s_gender),
        "signer_fio_short": fio_h.fio_short(s_last, s_first, s_middle),
        "signer_fio_genitive": fio_h.fio_full(s_last, s_first, s_middle, fio_h.GENITIVE, s_gender),
        "signer_basis": company.acts_on_basis or "",
    }


def current_declensions(employee) -> dict:
    """The genitive/dative/accusative ФИО actually in force for this employee:
    the manual override on the card if set, otherwise the automatic declension.
    Manual overrides apply to every document of the employee (ТЗ §6.1 / user rule)."""
    last, first, middle = employee.last_name, employee.first_name, employee.middle_name or ""
    gender = employee.gender or "male"
    return {
        "fio_genitive": getattr(employee, "fio_genitive_override", None)
        or fio_h.fio_full(last, first, middle, fio_h.GENITIVE, gender),
        "fio_dative": getattr(employee, "fio_dative_override", None)
        or fio_h.fio_full(last, first, middle, fio_h.DATIVE, gender),
        "fio_accusative": getattr(employee, "fio_accusative_override", None)
        or fio_h.fio_full(last, first, middle, fio_h.ACCUSATIVE, gender),
    }


def build_employee_context(employee) -> dict:
    last, first, middle = employee.last_name, employee.first_name, employee.middle_name or ""
    decl = current_declensions(employee)
    return {
        "fio_full": fio_h.fio_full(last, first, middle),
        "fio_short": fio_h.fio_short(last, first, middle),
        "fio_genitive": decl["fio_genitive"],
        "fio_dative": decl["fio_dative"],
        "fio_accusative_upper": decl["fio_accusative"].upper(),
        "iin": employee.iin,
        "id_document": format_id_document(employee),
        "address_actual": employee.actual_address or "",
        "phone": employee.phone or "",
    }


def build_employment_context(employment) -> dict:
    salary = employment.salary or 0
    months = employment.probation_months or 0
    probation_end = ""
    if months and employment.start_date:
        # испытательный "с start по end": end = start + N месяцев − 1 день
        probation_end = _short(add_months(employment.start_date, months) - _one_day())
    return {
        "position": employment.position_ru,
        "department": employment.department or "",
        "start_date_words": _words(employment.start_date),
        "start_date_short": _short(employment.start_date),
        "salary_figures": format_figures(salary),
        "salary_words_ru": getattr(employment, "salary_words_override", None)
        or ru_int_to_words(int(salary)),
        "probation_months": months,
        "probation_months_words": ru_int_to_words(months) if months else "",
        "probation_end_date_short": probation_end,
        "hours_per_week": _num(employment.hours_per_week),
        "work_from": employment.work_time_from or "",
        "work_to": employment.work_time_to or "",
        "lunch_from": employment.lunch_from or "",
        "lunch_to": employment.lunch_to or "",
        "days_off": employment.days_off or "",
    }


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


# --- deductions (заявление о налоговых вычетах, ТЗ §4.5) ---------------------

# Exact wording supplied by the client — do not paraphrase.
DEDUCTION_TEXTS = {
    "social_payments": "Налоговый вычет социальных платежей (обязательные пенсионные взносы, взносы на обязательное социальное медицинское страхование).",
    "base_30_mrp": "Базовый налоговый вычет в размере 30-кратного месячного расчётного показателя за каждый календарный месяц.",
    "social_882": "Социальный налоговый вычет в размере 882-кратного месячного расчётного показателя.",
    "social_5000": "Социальный налоговый вычет в размере 5 000-кратного месячного расчётного показателя.",
}
_SOCIAL_KEYS = ("social_882", "social_5000")


def build_deductions_context(selection: List[str], apply_from: Optional[date]) -> dict:
    """selection is an ordered list of DEDUCTION_TEXTS keys."""
    return {
        "list": [DEDUCTION_TEXTS[k] for k in selection if k in DEDUCTION_TEXTS],
        "apply_from_words": _words(apply_from),
        "has_social": any(k in _SOCIAL_KEYS for k in selection),
    }


# --- assembled contexts -----------------------------------------------------

def build_deduction_application_context(
    company, employee, selection: List[str],
    apply_from: Optional[date], application_date: Optional[date],
) -> dict:
    """Full context for zayavlenie_vychety_ipn.docx (ТЗ §4.5)."""
    return {
        "company": build_company_context(company),
        "employee": build_employee_context(employee),
        "deductions": build_deductions_context(selection, apply_from),
        "application": {"date_words": _words(application_date)},
    }


def build_prikaz_preview(company, employee, employment, hr_responsible_fio: str = "") -> dict:
    """Preview payload for the form: the full rendered context plus the auto-generated
    values the accountant most often edits, grouped by where the edit is PERSISTED
    (ТЗ §6, §8):
      * employee — ФИО in three cases (saved to the employee card, reused everywhere);
      * employment — position and the salary-in-words (saved to this hiring).
    Editing any of them flows into the generated document via the same context.
    """
    ctx = build_order_context(company, employee, employment, hr_responsible_fio)
    return {
        "context": ctx,
        "editable": {
            "employee": current_declensions(employee),
            "employment": {
                "position_ru": ctx["employment"]["position"],
                "salary_words_ru": ctx["employment"]["salary_words_ru"],
            },
        },
    }


def build_order_context(company, employee, employment, hr_responsible_fio: str = "") -> dict:
    """Full context for prikaz_o_prieme.docx (ТЗ §4.4)."""
    return {
        "company": build_company_context(company),
        "employee": build_employee_context(employee),
        "employment": build_employment_context(employment),
        "order": {
            "number": employment.order_number or "",
            "date_words": _words(employment.order_date),
        },
        "contract": {
            "number": employment.contract_number or "",
            "date_short": _short(employment.contract_date),
        },
        "application": {
            "date_short": _short(employment.application_date),
            "date_words": _words(employment.application_date),
        },
        "hr": {"responsible_fio": hr_responsible_fio or ""},
    }
