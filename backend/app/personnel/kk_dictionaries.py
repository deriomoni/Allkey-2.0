"""Small Russian→Kazakh reference dictionaries for the bilingual трудовой договор.

These cover CLOSED, mechanical translations so the accountant doesn't translate
them by hand: city names, days-off, working-conditions and the basis-of-authority
noun. Free-text fields (ФИО, должность, адрес, workplace) stay manual.

Everything here is data — extend the dicts, no logic change. The Kazakh texts are
proofread by a native speaker.
"""
from __future__ import annotations

import re


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text if text is not None else "").strip().lower())


# --- cities -----------------------------------------------------------
CITY_KZ = {
    "алматы": "Алматы",
    "астана": "Астана",
    "шымкент": "Шымкент",
    "караганда": "Қарағанды",
    "қарағанды": "Қарағанды",
    "актобе": "Ақтөбе",
    "тараз": "Тараз",
    "павлодар": "Павлодар",
    "усть-каменогорск": "Өскемен",
    "семей": "Семей",
    "атырау": "Атырау",
    "костанай": "Қостанай",
    "кызылорда": "Қызылорда",
    "уральск": "Орал",
    "петропавловск": "Петропавл",
    "актау": "Ақтау",
    "туркестан": "Түркістан",
    "кокшетау": "Көкшетау",
    "талдыкорган": "Талдықорған",
    "экибастуз": "Екібастұз",
}


def kk_city(city) -> str:
    return CITY_KZ.get(_norm(city), str(city or "").strip())


# --- days off (translate each day name in the phrase) -----------------
_DAY_KZ = {
    "понедельник": "дүйсенбі",
    "вторник": "сейсенбі",
    "среда": "сәрсенбі",
    "четверг": "бейсенбі",
    "пятница": "жұма",
    "суббота": "сенбі",
    "воскресенье": "жексенбі",
}


def kk_days_off(text) -> str:
    result = str(text or "")
    for ru, kk in _DAY_KZ.items():
        result = re.sub(ru, kk, result, flags=re.IGNORECASE)
    return re.sub(r"\bи\b", "және", result, flags=re.IGNORECASE)


# --- working conditions (by keyword) ----------------------------------
_CONDITIONS_KZ = [
    ("нормальн", "қалыпты"),
    ("вредн", "зиянды"),
    ("тяжёл", "ауыр"),
    ("тяжел", "ауыр"),
    ("опасн", "қауіпті"),
]


def kk_conditions(text) -> str:
    n = _norm(text)
    for key, kk in _CONDITIONS_KZ:
        if key in n:
            return kk
    return str(text or "").strip()


# --- basis of authority -----------------------------------------------
_BASIS_KZ = [
    ("устав", "Жарғы"),
    ("доверен", "сенімхат"),
    ("положен", "Ереже"),
]


def kk_basis(text) -> str:
    n = _norm(text)
    for key, kk in _BASIS_KZ:
        if key in n:
            return kk
    return str(text or "").strip()
