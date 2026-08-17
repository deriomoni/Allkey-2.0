"""First-name declension EXCEPTIONS — override the ending+gender rule in fio.py.

The rule (`fio._rule_decline_first`) declines the regular cases correctly,
including the common Kazakh patterns (Динара→Динары, Ерболат→Ерболата, женские
имена на согласную не склоняются, Абай→Абая). This table is ONLY for names the
rule gets WRONG, and it takes priority over the rule. Today that's mostly Russian
names with a fleeting vowel or ё (Павел→Павла, Пётр→Петра, Лев→Льва); add Kazakh
exceptions here too if the rule ever mis-declines one.

It is DATA, not logic — extend it freely. Values:
  * a dict {case: form} — a declinable exception (genitive/dative/accusative);
  * None — an indeclinable name (stays unchanged in every case).
Keys are lowercased. For a case not stored, the listed name is left unchanged.
"""
from __future__ import annotations

from typing import Dict, Optional, Union

NAME_FORMS: Dict[str, Optional[Dict[str, str]]] = {
    # Русские имена с беглой гласной / ё — правило по окончанию их не берёт.
    "пётр": {"genitive": "Петра", "dative": "Петру", "accusative": "Петра"},
    "петр": {"genitive": "Петра", "dative": "Петру", "accusative": "Петра"},
    "павел": {"genitive": "Павла", "dative": "Павлу", "accusative": "Павла"},
    "лев": {"genitive": "Льва", "dative": "Льву", "accusative": "Льва"},
    "любовь": {"genitive": "Любови", "dative": "Любови", "accusative": "Любовь"},
}

_MISSING = object()
MISSING = _MISSING


def form(name: str, case: str) -> Union[str, None, object]:
    """Look up an exception.

    Returns the declined form (str); None if listed but unchanged for this case
    (indeclinable / case not stored); or the sentinel MISSING if the name is not
    an exception at all (caller falls back to the rule).
    """
    entry = NAME_FORMS.get((name or "").strip().lower(), _MISSING)
    if entry is _MISSING:
        return _MISSING
    if entry is None:
        return None
    return entry.get(case)
