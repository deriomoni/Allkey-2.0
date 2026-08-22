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


# --- company name: organizational form → Kazakh, moved to the end ------
# Название (в кавычках или фамилия для ИП) не меняется, меняется только форма.
ORG_FORMS = {
    "тоо": "ЖШС",
    "ао": "АҚ",
    "ип": "ЖК",
    "филиал": "Филиал",
    "представительство": "Өкілдік",
    "учреждение": "Мекеме",
    "общественное объединение": "Қоғамдық бірлестік",
    "производственный кооператив": "Өндірістік кооператив",
    "крестьянское хозяйство": "Шаруа қожалығы",
}


def kk_company_name(name_ru) -> str:
    """«ТОО «X»» → ««X» ЖШС», «ИП Петров» → «Петров ЖК». Если ведущая ОПФ не
    распознана — возвращаем как есть (пользователь поправит)."""
    name = str(name_ru or "").strip()
    if not name:
        return ""
    low = name.lower()
    for form in sorted(ORG_FORMS, key=len, reverse=True):   # многословные ОПФ первыми
        if low.startswith(form):
            after = name[len(form):]
            if after[:1] in ("", " ", "\u00ab", "\u201c", '"'):   # граница слова
                rest = after.strip()
                kk = ORG_FORMS[form]
                return f"{rest} {kk}".strip()
    return name


# --- address: service words → Kazakh, generic moved AFTER the name -----
ADDRESS_WORDS = {
    "г.": "қ.", "г": "қ.", "город": "қ.",
    "улица": "көшесі", "ул.": "көшесі", "ул": "көшесі",
    "проспект": "даңғылы", "пр.": "даңғылы", "пр": "даңғылы",
    "микрорайон": "шағын ауданы", "мкр.": "шағын ауданы", "мкр": "шағын ауданы",
    "дом": "үй", "д.": "үй",
    "квартира": "пәтер", "кв.": "пәтер", "кв": "пәтер",
    "офис": "кеңсе", "оф.": "кеңсе",
    "здание": "ғимарат",
    "переулок": "тұйық көше", "пер.": "тұйық көше",
    "район": "ауданы",
    "область": "облысы", "обл.": "облысы",
    "село": "ауылы", "с.": "ауылы",
    "посёлок": "кенті", "поселок": "кенті", "пос.": "кенті",
    "шоссе": "тас жолы",
    "бульвар": "гүлзары", "бул.": "гүлзары",
    "площадь": "алаңы", "пл.": "алаңы",
}


def _kk_address_segment(seg, city_kz) -> str:
    tokens = seg.split()
    if not tokens:
        return seg
    kk = ADDRESS_WORDS.get(tokens[0].lower())
    if kk is None:
        return seg                       # нет служебного слова (номер дома и т.п.) — как есть
    rest = " ".join(tokens[1:]).strip()
    if kk == "қ.":                       # сегмент города — берём из city_kz (или переводим)
        rest = (city_kz or kk_city(rest)).strip()
    if not rest:
        return kk
    return f"{rest} {kk}"                 # казахский порядок: имя, затем служебное слово


def kk_address(address_ru, city_kz="") -> str:
    """«г. Алматы, ул. Абая, 10» → «Алматы қ., Абая көшесі, 10». Название улицы не
    склоняется (остаётся как ввёл пользователь)."""
    addr = str(address_ru or "").strip()
    if not addr:
        return ""
    return ", ".join(_kk_address_segment(s.strip(), city_kz) for s in addr.split(",") if s.strip())
