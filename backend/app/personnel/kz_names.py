"""Curated declensions of Kazakh first names.

pymorphy3 is unreliable for Kazakh given names — it mis-genders some (Жанар,
Аружан, Сауле → «мужской»), misreads others (Әсем → мн.ч., Дана → причастие).
So Kazakh names are declined ONLY from this vetted table; a name that is not
here and has no reliable pymorphy parse is left UNCHANGED (no guessing).

Extend this dict — it is data, not logic. Values:
  * a dict {case: form}  — declinable name (Russian case keys used by fio.py);
  * None                 — indeclinable name (stays as-is in every case).
Only genitive/dative/accusative are stored (the cases documents use); for any
other case a listed name is left unchanged.
"""
from __future__ import annotations

from typing import Dict, Optional, Union

# case keys match app.personnel.helpers.fio: genitive / dative / accusative
KZ_NAME_FORMS: Dict[str, Optional[Dict[str, str]]] = {
    # --- мужские, склоняются (согласная на конце) ---
    "нұрлан": {"genitive": "Нұрлана", "dative": "Нұрлану", "accusative": "Нұрлана"},
    "ержан": {"genitive": "Ержана", "dative": "Ержану", "accusative": "Ержана"},
    "тимур": {"genitive": "Тимура", "dative": "Тимуру", "accusative": "Тимура"},
    "бекзат": {"genitive": "Бекзата", "dative": "Бекзату", "accusative": "Бекзата"},
    "дидар": {"genitive": "Дидара", "dative": "Дидару", "accusative": "Дидара"},
    "асхат": {"genitive": "Асхата", "dative": "Асхату", "accusative": "Асхата"},
    # --- женские на -а, склоняются ---
    "мадина": {"genitive": "Мадины", "dative": "Мадине", "accusative": "Мадину"},
    "дана": {"genitive": "Даны", "dative": "Дане", "accusative": "Дану"},
    # --- женские, НЕ склоняются (согласная / -е) ---
    "әсем": None,
    "жанар": None,
    "аружан": None,
    "асель": None,
    "сауле": None,
    "айгүл": None,
    "айгуль": None,
    "гүлназ": None,
    "назгүл": None,
}

_MISSING = object()


def form(name: str, case: str) -> Union[str, None, object]:
    """Look up a name.

    Returns:
      * the declined form (str) for a listed declinable name in this case;
      * None — the name is listed but should stay unchanged (indeclinable, or
        this case is not stored);
      * the sentinel `MISSING` — the name is not in the table at all (caller
        falls back to pymorphy / leaves unchanged).
    """
    entry = KZ_NAME_FORMS.get((name or "").strip().lower(), _MISSING)
    if entry is _MISSING:
        return _MISSING
    if entry is None:
        return None
    return entry.get(case)  # None if this case not stored → caller keeps original


MISSING = _MISSING
