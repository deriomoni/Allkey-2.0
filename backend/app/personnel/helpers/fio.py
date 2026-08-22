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
    (Абдул-Керим), so capitalize each hyphen-separated part.

    Также выравниваем ё/е к исходному написанию: pymorphy нормализует «е» в «ё»
    и возвращает «семёнову» там, где пользователь написал «Семенова». Написание
    должно совпадать с введённым — если в исходном слове нет ё, убираем ё из формы."""
    if "ё" not in sample.lower():
        inflected = inflected.replace("ё", "е")
    if sample[:1].isupper():
        return "-".join(part.capitalize() for part in inflected.split("-"))
    return inflected


# Гласные окончания (кроме -а/-я), после которых имя НЕ склоняется.
# Казахские гласные ә, ө, ү, ұ, і — по фонетике гласные.
_VOWELS_NODECL = set("еёиоуюыэәөүұі")
_GEN_A_SOFT_AFTER = set("гкхжчшщ")   # родительный -а → -и после этих согласных
_INSTR_A_SOFT_AFTER = set("жчшщц")   # творительный -а → -ей после шипящих/ц


def _rule_decline_first(name: str, case: str, gender: str) -> str:
    """Склонение имени по окончанию и полу — норма русской грамматики для
    иноязычных имён (не угадывание):
      * -а/-я → 1-е склонение (независимо от пола): Динара→Динары, Мұстафа→Мұстафы;
      * согласный или -й/-ь, мужской → 2-е склонение: Ерболат→Ерболата, Абай→Абая;
      * согласный, женский → не склоняется: Гүлнар, Ботагөз;
      * -е,-и,-о,-у,-ю,-ы и казахские ә,ө,ү,ұ,і → не склоняются у обоих: Сауле.
    """
    n = name.strip()
    if not n:
        return n
    low = n.lower()
    last = low[-1]
    prev = low[-2] if len(low) > 1 else ""

    if last == "а":
        stem = n[:-1]
        if case == GENITIVE:
            return stem + ("и" if prev in _GEN_A_SOFT_AFTER else "ы")
        if case == DATIVE:
            return stem + "е"
        if case == ACCUSATIVE:
            return stem + "у"
        if case == INSTRUMENTAL:
            return stem + ("ей" if prev in _INSTR_A_SOFT_AFTER else "ой")
        if case == PREPOSITIONAL:
            return stem + "е"
        return n
    if last == "я":
        stem = n[:-1]
        vowel_before = prev in "аеёиоуыэюяәөүұі" or prev == "ь"  # -ия/-ья → дат/предл -ии
        if case == GENITIVE:
            return stem + "и"
        if case == DATIVE:
            return stem + ("и" if vowel_before else "е")
        if case == ACCUSATIVE:
            return stem + "ю"
        if case == INSTRUMENTAL:
            return stem + "ей"
        if case == PREPOSITIONAL:
            return stem + ("и" if vowel_before else "е")
        return n
    if last in _VOWELS_NODECL:
        return n
    # согласный или -й/-ь
    if gender != "male":
        return n
    if last in "йь":
        stem = n[:-1]
        if case in (GENITIVE, ACCUSATIVE):
            return stem + "я"
        if case == DATIVE:
            return stem + "ю"
        if case == INSTRUMENTAL:
            return stem + "ем"
        if case == PREPOSITIONAL:
            return stem + "е"
        return n
    # твёрдый согласный (в т.ч. казахские ғ, қ, ң, һ)
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

      * Kazakh -ұлы/-қызы names — indeclinable in any position.
      * First names — name_exceptions table first, then the ending+gender rule
        above; pymorphy is NOT used for first names (it mis-genders many Kazakh
        names; the rule is more reliable). Hyphenated names decline part by part.
      * Surnames — a pymorphy Surn parse of the MATCHING gender first, then the
        SAME ending+gender rule as first names (so «Оспан» declines for a man —
        Оспана — and stays for a woman); Russian «Ким»/«Цой» handled by pymorphy.
      * Patronymics — a pymorphy Patr parse of the matching gender, else unchanged
        (-ұлы/-қызы already handled above; -ович/-евич are in pymorphy).
    Every result is editable downstream.
    """
    from app.personnel import name_exceptions

    part = (part or "").strip()
    if not part or case == NOMINATIVE:
        return part
    if _is_kazakh_indeclinable(part):
        return part

    grammeme = _CASE_GRAMMEME.get(case)
    if grammeme is None:
        return part

    if kind == "first":
        if "-" in part:
            return "-".join(_decline_part(seg, "first", case, gender) for seg in part.split("-"))
        looked_up = name_exceptions.form(part, case)
        if looked_up is not name_exceptions.MISSING:
            return looked_up if looked_up else part   # exception form, or indeclinable
        return _rule_decline_first(part, case, gender)

    gender_gr = "masc" if gender == "male" else "femn"
    parses = _morph().parse(part)
    # Surname/patronymic: a proper-name parse of the MATCHING gender is trusted.
    gendered = [p for p in parses if _PART_TAG[kind] in p.tag and gender_gr in p.tag]
    if gendered:
        result = gendered[0].inflect({grammeme, gender_gr})
        if result is not None:
            return _match_case(part, result.word)
    # No pymorphy parse: surnames fall back to the same ending+gender rule
    # (мужская на согласный склоняется, женская нет). Patronymics stay unchanged.
    if kind == "last":
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
