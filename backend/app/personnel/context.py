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
from decimal import Decimal
from typing import List, Optional

from app.personnel import kk_dictionaries as kkd
from app.personnel.helpers import fio as fio_h
from app.personnel.helpers.dates import date_in_words, date_short, add_months, month_year_in_words
from app.personnel.helpers.numbers import (
    ru_int_to_words, kk_int_to_words, format_figures, pluralize_ru,
)

_UNIT_RU = {"year": ("год", "года", "лет"), "month": ("месяц", "месяца", "месяцев")}
_UNIT_KZ = {"year": "жыл", "month": "ай"}


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
        "gender": employee.gender or "male",   # для будущей подстановки одной родовой формы
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
        # Вычет применяется за календарный МЕСЯЦ (ст. 403 НК РК): «начиная с августа 2026 года».
        "apply_from_words": month_year_in_words(apply_from) if apply_from else "",
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


def build_matotvet_context(company, employee, employment, liability) -> dict:
    """Context for dogovor_matotvetstvennost.docx (universal form; опись — отдельный акт).
    liability needs only number + date_words (ТЗ §4.1)."""
    return {
        "company": build_company_context(company),
        "employee": build_employee_context(employee),
        "employment": build_employment_context(employment),
        "liability": {
            "number": getattr(liability, "number", "") or "",
            "date_words": _words(getattr(liability, "doc_date", None)),
        },
    }


def build_nekonkurencii_context(company, employee, employment, nc) -> dict:
    """Context for dogovor_nekonkurencii.docx. Terms are fields, not constants (§2 п.7)."""
    return {
        "company": build_company_context(company),
        "employee": build_employee_context(employee),
        "employment": build_employment_context(employment),
        "nc": {
            "number": nc.number, "date_words": _words(nc.doc_date),
            "term_noncompete": nc.term_noncompete, "term_nonsolicit": nc.term_nonsolicit,
            "term_confidential": nc.term_confidential, "territory": nc.territory,
            "activity": nc.activity, "competitors": nc.competitors, "penalty": nc.penalty,
        },
    }


def build_akt_context(company, employee, employment, act, inventory, liability) -> dict:
    """Context for akt_priema_peredachi.docx. Опись rows and their totals are computed
    from the inventory (name/code/unit/qty/price); transferor = company signer,
    receiver = employee — derived, not re-typed."""
    comp = build_company_context(company)
    emp = build_employee_context(employee)

    items = []
    total = Decimal(0)
    for it in inventory:
        qty = it.qty or Decimal(0)
        price = it.price or Decimal(0)
        line_sum = qty * price
        total += line_sum
        items.append({
            "name": it.name, "code": it.code, "unit": it.unit,
            "qty": _num(qty), "price": format_figures(price), "sum": format_figures(line_sum),
        })
    count = len(items)

    return {
        "company": comp,
        "liability": {
            "number": getattr(liability, "number", "") or "",
            "date_short": _short(getattr(liability, "doc_date", None)),
        },
        "items": items,
        "act": {
            "number": act.number, "date_words": _words(act.doc_date),
            "transferor_position": comp["signer_position"],
            "transferor_position_genitive": comp["signer_position_genitive"],
            "transferor_fio_genitive": comp["signer_fio_genitive"],
            "transferor_fio_short": comp["signer_fio_short"],
            "receiver_position": employment.position_ru,
            "receiver_fio_full": emp["fio_full"],
            "receiver_iin": emp["iin"],
            "receiver_fio_short": emp["fio_short"],
            "basis": getattr(act, "basis", "") or "",   # свободное «Основание» (пусто → не выводится)
            "total_figures": format_figures(total),
            "total_words": ru_int_to_words(int(total)),
            "items_count": count,
            "items_count_words": ru_int_to_words(count),
            "notes": act.notes,
            "commission": [{"position": m.position, "fio_short": m.fio_short} for m in act.commission],
        },
    }


def build_perechen_context(company, perechen, nc) -> dict:
    """Context for prikaz_perechen_nekonkurencii.docx (приказ об утверждении перечня)."""
    comp = build_company_context(company)
    last, first, middle = split_fio(perechen.responsible_fio)
    responsible_accusative = fio_h.fio_full(last, first, middle, fio_h.ACCUSATIVE, "male")
    return {
        "company": comp,
        "order": {
            "number": perechen.number, "date_words": _words(perechen.doc_date), "date_short": _short(perechen.doc_date),
            "responsible_position": perechen.responsible_position,
            "responsible_fio_accusative": responsible_accusative,
            "control": perechen.control,
        },
        "nc": {
            "term_noncompete": nc.term_noncompete if nc else "",
            "term_nonsolicit": nc.term_nonsolicit if nc else "",
        },
        "positions": [{"name": p.name, "reason": p.reason} for p in perechen.positions],
        "acquainted": [{"position": a.position, "fio_short": a.fio_short} for a in perechen.acquainted],
    }


def _kk_words_date(d: Optional[date]) -> str:
    return date_in_words(d, "kk") if d else ""


def _contract_term(count: int, unit: str) -> "tuple[str, str]":
    """('1 (один) год', '1 (бір) жыл') from a structured term — so term_kz is a
    computed helper value, not a manual field."""
    unit_ru = pluralize_ru(count, _UNIT_RU.get(unit, _UNIT_RU["year"]))
    unit_kz = _UNIT_KZ.get(unit, _UNIT_KZ["year"])
    return (f"{count} ({ru_int_to_words(count)}) {unit_ru}",
            f"{count} ({kk_int_to_words(count)}) {unit_kz}")


def build_polozhenie_pd_context(company, policy) -> dict:
    """Context for polozhenie_personalnye_dannye.docx (§4.6) — почти статичный акт,
    нужны только наименование и реквизиты утверждающего приказа."""
    return {
        "company": {"name_full": build_company_context(company)["name_full"]},
        "policy": {"order_number": policy.order_number, "order_date_short": _short(policy.doc_date)},
    }


def build_soglasie_context(company, employee, employment, consent) -> dict:
    """Context for soglasie_personalnye_dannye.docx (§4.7) — согласие работника
    на сбор и обработку ПД. Все реквизиты — редактируемые поля формы."""
    comp = build_company_context(company)
    emp = build_employee_context(employee)
    return {
        "company": {
            "name_full": comp["name_full"], "bin": comp["bin"],
            "city": comp["city"], "address": comp["address"],
        },
        "employee": {
            "fio_full": emp["fio_full"], "fio_short": emp["fio_short"], "iin": emp["iin"],
        },
        "employment": {"position": employment.position_ru},
        "consent": {
            "date_words": _words(consent.doc_date),
            "cross_border": bool(getattr(consent, "cross_border", False)),
            "cross_border_countries": getattr(consent, "cross_border_countries", "") or "",
            "cross_border_purpose": getattr(consent, "cross_border_purpose", "") or "",
            "responsible_position": getattr(consent, "responsible_position", "") or "",
            "responsible_fio": getattr(consent, "responsible_fio", "") or "",
            "responsible_contacts": getattr(consent, "responsible_contacts", "") or "",
        },
        "recipients": [
            {"name": r.name, "bin": getattr(r, "bin", "") or "",
             "purpose": r.purpose, "scope": r.scope}
            for r in (consent.recipients or [])
        ],
    }


def build_prikaz_pd_context(company, policy) -> dict:
    """Context for prikaz_otvetstvennyy_pd.docx (§4.6) — приказ о назначении
    ответственного за обработку ПД (ответственный склоняется в винительный)."""
    comp = build_company_context(company)
    last, first, middle = split_fio(policy.responsible_fio)
    return {
        "company": {
            "name_full": comp["name_full"], "bin": comp["bin"], "city": comp["city"],
            "signer_position": comp["signer_position"], "signer_fio_short": comp["signer_fio_short"],
        },
        "policy": {
            "order_number": policy.order_number, "order_date_words": _words(policy.doc_date),
            "responsible_fio_accusative": fio_h.fio_full(last, first, middle, fio_h.ACCUSATIVE, "male"),
            "responsible_position_accusative": fio_h.inflect_phrase(policy.responsible_position, fio_h.ACCUSATIVE, "male"),
            "deadline_short": _short(policy.deadline), "control": policy.control,
        },
        "acquainted": [{"position": a.position, "fio_short": a.fio_short} for a in policy.acquainted],
    }


def build_trudovoy_context(company, employee, employment, contract) -> dict:
    """Full bilingual context for trudovoy_dogovor.docx (ТЗ §4.2, §2.3).

    Kazakh forms of numbers/dates/term are computed by our helpers; days-off,
    conditions, city and basis come from kk_dictionaries; the remaining Kazakh
    strings (ФИО/должность/адрес/workplace) are manual translations passed in.
    """
    comp = build_company_context(company)
    emp = build_employee_context(employee)
    salary = employment.salary or 0
    months = employment.probation_months or 0

    term = term_kz = end_words = end_words_kz = ""
    if contract.kind == "fixed":
        if contract.term_count:
            term, term_kz = _contract_term(contract.term_count, contract.term_unit)
        end_words = _words(contract.end_date)
        end_words_kz = _kk_words_date(contract.end_date)

    return {
        "company": {
            "name_full": comp["name_full"], "name_full_kz": company.name_kk or "",
            "bin": comp["bin"], "city": comp["city"], "city_kz": kkd.kk_city(company.city),
            "address": comp["address"], "address_kz": getattr(company, "address_kz", "") or "",
            "signer_position_genitive": comp["signer_position_genitive"],
            "signer_position_kz": getattr(company, "signer_position_kz", "") or "",
            "signer_fio_genitive": comp["signer_fio_genitive"],
            "signer_fio_kz": company.director_fio_kk or "",
            "signer_fio_short": comp["signer_fio_short"],
            "signer_basis": comp["signer_basis"], "signer_basis_kz": kkd.kk_basis(company.acts_on_basis),
        },
        "employee": {
            "fio_full": emp["fio_full"], "fio_full_kz": getattr(employee, "fio_full_kz", "") or "",
            "fio_short": emp["fio_short"], "iin": emp["iin"],
            "id_document": emp["id_document"], "id_document_kz": getattr(employee, "id_document_kz", "") or "",
            "address_actual": emp["address_actual"],
        },
        "employment": {
            "position": employment.position_ru, "position_kz": employment.position_kk or "",
            "workplace": getattr(employment, "workplace", "") or "",
            "workplace_kz": getattr(employment, "workplace_kz", "") or "",
            "start_date_words": _words(employment.start_date),
            "start_date_words_kz": _kk_words_date(employment.start_date),
            "probation_months": months,
            "probation_months_words": ru_int_to_words(months) if months else "",
            "probation_months_words_kz": kk_int_to_words(months) if months else "",
            "hours_per_day": _num(employment.hours_per_day), "hours_per_week": _num(employment.hours_per_week),
            "work_from": employment.work_time_from or "", "work_to": employment.work_time_to or "",
            "lunch_from": employment.lunch_from or "", "lunch_to": employment.lunch_to or "",
            "days_off": employment.days_off or "", "days_off_kz": kkd.kk_days_off(employment.days_off or ""),
            "vacation_days": employment.vacation_days or 0,
            "conditions": getattr(employment, "conditions", "") or "",
            "conditions_kz": kkd.kk_conditions(getattr(employment, "conditions", "")),
            "salary_figures": format_figures(salary),
            "salary_words_ru": ru_int_to_words(int(salary)),
            "salary_words_kz": kk_int_to_words(int(salary)),
            # gross|net — меняет формулировки п. 4.1/4.2 в шаблоне; сумма подставляется как есть
            "salary_kind": getattr(employment, "salary_kind", "gross") or "gross",
        },
        "contract": {
            "number": contract.number, "date_words": _words(contract.doc_date),
            "date_words_kz": _kk_words_date(contract.doc_date), "date_short": _short(contract.doc_date),
            "kind": contract.kind, "term": term, "term_kz": term_kz,
            "end_date_words": end_words, "end_date_words_kz": end_words_kz,
            "task": contract.task, "task_kz": contract.task_kz,
            "confidential_years": contract.confidential_years,
        },
    }


# Приказу о приёме НЕ нужны (есть в трудовом договоре; в приказе создавали бы
# лишнее разглашение оклада и риск расхождения по режиму): оклад и режим работы,
# а также ФИО в дательном. В build_employment/employee_context они остаются —
# трудовой договор их использует.
_ORDER_DROP_EMPLOYMENT = (
    "salary_figures", "salary_words_ru", "hours_per_week",
    "work_from", "work_to", "lunch_from", "lunch_to", "days_off",
)


def build_order_context(company, employee, employment, hr_responsible_fio: str = "") -> dict:
    """Context for prikaz_o_prieme.docx (§4.4). Без оклада и режима работы —
    их место в трудовом договоре и ПВТР (см. _ORDER_DROP_EMPLOYMENT)."""
    emp = build_employee_context(employee)
    emp.pop("fio_dative", None)
    empl = build_employment_context(employment)
    for key in _ORDER_DROP_EMPLOYMENT:
        empl.pop(key, None)
    return {
        "company": build_company_context(company),
        "employee": emp,
        "employment": empl,
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
