"""Russian declension of a person's ФИО (ТЗ §6.1).

Needed for the Russian documents and headers: genitive ("от Климова Василия
Александровича"), dative ("Климову Василию Александровичу"), accusative
("принять Климова Василия Александровича"). The Kazakh column of the templates
uses the nominative form (verified against the трудовой договор template), so
Kazakh names are never declined here.

Declension uses `pymorphy3`: for each name part we pick the parse tagged as a
surname / first name / patronymic (Surn / Name / Patr) with the matching gender,
then inflect it to the target case. Kazakh-style patronymics on -ұлы/-қызы (and
their common cyrillic spellings) are treated as indeclinable and returned
unchanged. Every generated value is surfaced as an editable field downstream, so
the accountant can always correct an edge case.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict

# Cases we support, keyed by the strings the API/schemas use.
NOMINATIVE = "nominative"
GENITIVE = "genitive"
DATIVE = "dative"
ACCUSATIVE = "accusative"
INSTRUMENTAL = "instrumental"
PREPOSITIONAL = "prepositional"

# case string -> pymorphy grammeme
_CASE_GRAMMEME = {
    GENITIVE: "gent",
    DATIVE: "datv",
    ACCUSATIVE: "accs",
    INSTRUMENTAL: "ablt",
    PREPOSITIONAL: "loct",
}

# name part -> pymorphy tag that marks it a proper name of that kind
_PART_TAG = {"last": "Surn", "first": "Name", "middle": "Patr"}

# Kazakh patronymic / surname endings that must not be declined by Russian rules.
_KZ_INDECLINABLE_ENDINGS = ("ұлы", "қызы", "тегі", "улы", "кызы")


def _is_kazakh_indeclinable(name: str) -> bool:
    return name.strip().lower().endswith(_KZ_INDECLINABLE_ENDINGS)


@lru_cache(maxsize=1)
def _morph():
    """Lazily build the (heavy) MorphAnalyzer once per process."""
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


def _match_case(sample: str, inflected: str) -> str:
    """Restore capitalization: pymorphy returns lowercase; names may be hyphenated
    (Абдул-Керим), so capitalize each hyphen-separated part."""
    if sample[:1].isupper():
        return "-".join(part.capitalize() for part in inflected.split("-"))
    return inflected


_GEN_SOFT_AFTER = set("гкхжчшщ")  # после этих согласных родительный -а → -и


def _rule_decline_first(name: str, case: str, gender: str) -> str:
    """Небольшое правило склонения ИМЕНИ, когда pymorphy не знает его как имя
    (частый случай для казахских имён). Управляется полом.

    -а/-я → женская 1-е склонение (Дана→Даны, Дария→Дарии); мужское имя на
    твёрдый согласный → Дидар→Дидара; женское имя на согласный (Айгүл) и имена
    на и/о/у/ю/е — несклоняемы. Результат всегда редактируем в форме."""
    n = name.strip()
    if not n:
        return n
    low = n.lower()
    last = low[-1]
    if last in "иоуюеэё":
        return n
    if last in "ая":  # женский тип (для обоих полов, если имя на -а/-я)
        stem, soft = n[:-1], last == "я"
        prev = low[-2] if len(low) > 1 else ""
        if case == GENITIVE:
            end = "и" if (soft or prev in _GEN_SOFT_AFTER) else "ы"
        elif case == DATIVE:
            end = "е"
        elif case == ACCUSATIVE:
            end = "ю" if soft else "у"
        elif case == INSTRUMENTAL:
            end = "ей" if soft else "ой"
        elif case == PREPOSITIONAL:
            end = "е"
        else:
            return n
        return stem + end
    # окончание на согласный
    if gender != "male":
        return n            # женское имя на согласный (Айгүл, Гүлназ) не склоняется
    if last in "йь":
        return n            # мягкие окончания — не рискуем
    if case in (GENITIVE, ACCUSATIVE):
        return n + "а"
    if case == DATIVE:
        return n + "у"
    if case == INSTRUMENTAL:
        return n + "ом"
    if case == PREPOSITIONAL:
        return n + "е"
    return n


def _decline_part(part: str, kind: str, case: str, gender: str) -> str:
    """Decline one name part. `kind` is 'last' | 'first' | 'middle'.

    Nominative and Kazakh-indeclinable surnames are returned as-is. If pymorphy
    cannot inflect (unknown name / no matching form), the original is returned —
    the field stays editable downstream.
    """
    part = (part or "").strip()
    if not part or case == NOMINATIVE:
        return part
    # Kazakh -ұлы/-қызы names are indeclinable in ANY position (surname OR
    # patronymic: «Жанатұлы» as отчество must stay unchanged in all cases).
    if _is_kazakh_indeclinable(part):
        return part

    grammeme = _CASE_GRAMMEME.get(case)
    if grammeme is None:
        return part

    gender_gr = "masc" if gender == "male" else "femn"
    parses = _morph().parse(part)
    # Use ONLY a parse tagged as this kind of proper name (Surn/Name/Patr), of the
    # matching gender — so the ИИН gender really drives declension. Do NOT fall
    # back to an arbitrary parse (that mangled «Оспан»→«оспана», «Дана»→«данной»).
    typed = [p for p in parses if _PART_TAG[kind] in p.tag]
    gendered = [p for p in typed if gender_gr in p.tag]
    chosen = gendered or typed
    if chosen:
        result = chosen[0].inflect({grammeme, gender_gr})
        return _match_case(part, result.word) if result is not None else part

    # No proper-name parse: first names (often Kazakh) get the small rule above;
    # surnames/patronymics stay unchanged (never mangle «Оспан»).
    if kind == "first":
        return _rule_decline_first(part, case, gender)
    return part


def decline_fio(
    last: str,
    first: str = "",
    middle: str = "",
    case: str = NOMINATIVE,
    gender: str = "male",
) -> Dict[str, str]:
    """Return the three name parts in the requested case as a dict."""
    return {
        "last": _decline_part(last, "last", case, gender),
        "first": _decline_part(first, "first", case, gender),
        "middle": _decline_part(middle, "middle", case, gender),
    }


def fio_full(
    last: str,
    first: str = "",
    middle: str = "",
    case: str = NOMINATIVE,
    gender: str = "male",
) -> str:
    """'Климова Василия Александровича' in the requested case."""
    parts = decline_fio(last, first, middle, case, gender)
    return " ".join(p for p in (parts["last"], parts["first"], parts["middle"]) if p)


def inflect_phrase(text: str, case: str, gender: str = "male") -> str:
    """Best-effort declension of a short noun phrase (e.g. a job title:
    'Генеральный директор' -> genitive 'Генерального директора').

    Used for the signer's position in the material-liability contract. Each token
    is inflected independently; unknown tokens are left as-is. Output is editable
    downstream, so approximate agreement on rare titles is acceptable.
    """
    text = (text or "").strip()
    if not text or case == NOMINATIVE:
        return text
    grammeme = _CASE_GRAMMEME.get(case)
    if grammeme is None:
        return text

    out = []
    for token in text.split():
        parses = _morph().parse(token)
        if not parses:
            out.append(token)
            continue
        result = parses[0].inflect({grammeme})
        out.append(_match_case(token, result.word) if result else token)
    return " ".join(out)


def fio_short(last: str, first: str = "", middle: str = "") -> str:
    """'Климов В.А.' — surname plus initials, nominative."""
    initials = ""
    if first:
        initials += f"{first.strip()[0].upper()}."
    if middle:
        initials += f"{middle.strip()[0].upper()}."
    last = (last or "").strip()
    return f"{last} {initials}".strip()
