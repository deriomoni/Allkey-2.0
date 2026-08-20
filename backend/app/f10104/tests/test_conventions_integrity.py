"""Целостность справочника конвенций: код страны, её название и её ставки.

Ошибка, ради которой написан этот файл, стоила бы реальных денег и не ловилась
ничем: записи Армении и Финляндии несли данные друг друга целиком. Причина —
список кодов стран и строки таблицы-источника связывались ПО ПОРЯДКУ, а порядок
разошёлся на две позиции. Ни типы, ни схема, ни чтение глазами такое не видят:
каждая запись по отдельности выглядит правдоподобно.

Отсюда два разных сторожа, и оба нужны:

  1. код страны ↔ её название — сверяется с независимым источником имён
     (`country_names.json`), который собирался отдельно и потому ценен;
  2. разобранные числа ↔ строка `raw` той же записи — именно этот сторож ловит
     случай, когда названия уже поправили, а числа ещё нет.

Второй важнее первого: в редакции 1.7.2 названия были обменены обратно, а числа
остались перепутанными, и первая проверка прошла бы зелёной.
"""
import re

from app.f10104.rules import get_country_names, get_rules


def rates() -> dict:
    return get_rules()["conventions"]["rates"]


def percentages(raw: str) -> set[float]:
    """Все проценты, упомянутые в исходной строке таблицы-источника."""
    return {float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", raw or "")}


# ── Сторож 1: код ↔ название ───────────────────────────────────────────────

# Одна страна называется по-разному в двух источниках законно: в анкете стоит
# аббревиатура, в таблице ставок — полное название. Пары перечислены явно,
# чтобы послабление было видно глазом, а не растворилось в правиле сравнения.
KNOWN_ALIASES = {
    "AE": ("ОАЭ", "Объединенные Арабские Эмираты"),
}


def test_every_convention_country_is_named_the_same_in_both_sources():
    """Название в справочнике ставок обязано совпадать с независимым списком имён.

    Расхождение здесь означает, что запись принадлежит другой стране — то есть
    её ставки тоже чужие.
    """
    names = get_country_names()["names"]
    expected = get_rules()["conventions"]["integrity_check"]["expected_names"]
    mismatched = []

    for iso, record in rates().items():
        want = expected.get(iso) or names.get(iso)
        got = record.get("country_ru")
        if iso in KNOWN_ALIASES and {want, got} <= set(KNOWN_ALIASES[iso]):
            continue
        if want and got and want.split()[-1].lower() not in got.lower() \
                and got.split()[-1].lower() not in want.lower():
            mismatched.append(f"{iso}: в ставках «{got}», в списке имён «{want}»")

    assert not mismatched, "; ".join(mismatched)


def test_all_convention_codes_have_a_rates_record():
    """Страна в списке конвенций без записи ставок — молчаливая дыра."""
    missing = [iso for iso in get_rules()["conventions"]["countries"]
               if iso not in rates()]
    assert not missing, missing


# ── Сторож 2: числа ↔ собственная строка raw ───────────────────────────────

def test_parsed_dividend_rates_match_their_own_source_string():
    """Разобранные ставки обязаны встречаться в строке, из которой разобраны.

    Именно эта проверка ловит перепутанные записи после того, как названия
    уже исправили: строка `raw` переезжает вместе с названием, а числа —
    отдельным полем, и рассинхрон остаётся невидимым.
    """
    wrong = []
    for iso, record in sorted(rates().items()):
        block = record.get("dividends") or {}
        raw = block.get("raw")
        if not raw or block.get("confidence") == "manual_review":
            continue
        source = percentages(raw)
        parsed = {v for v in (block.get("reduced_pct"), block.get("default_pct"))
                  if v is not None}
        if not parsed <= source:
            wrong.append(f"{iso} ({record.get('country_ru')}): "
                         f"разобрано {sorted(parsed)}, в строке «{raw}»")

    assert not wrong, "; ".join(wrong)


def test_flat_or_tiered_structure_matches_the_source_string():
    """Одна ставка в строке — ставка плоская. Несколько — со ступенью по доле.

    Ровно этот тест краснел бы на редакции 1.7.2: у Армении строка «10%»
    описывает плоскую ставку, а разобрана она была со ступенью 5/10/15,
    и наоборот у Финляндии.
    """
    wrong = []
    for iso, record in sorted(rates().items()):
        block = record.get("dividends") or {}
        raw = block.get("raw")
        if not raw or block.get("confidence") == "manual_review":
            continue
        parsed_is_flat = block.get("ownership_threshold_pct") is None
        source_is_flat = len(percentages(raw)) == 1
        if parsed_is_flat != source_is_flat:
            wrong.append(
                f"{iso} ({record.get('country_ru')}): строка «{raw}» описывает "
                f"{'плоскую ставку' if source_is_flat else 'ставку со ступенью'}, "
                f"а разобрана как {'плоская' if parsed_is_flat else 'со ступенью'}")

    assert not wrong, "; ".join(wrong)


# ── Две страны, на которых всё вскрылось ───────────────────────────────────

def test_armenia_is_flat_ten_percent():
    """Армения — плоские 10 %. Пороговая ставка здесь означала бы, что запись
    снова несёт чужие данные."""
    block = rates()["AM"]["dividends"]

    assert block["ownership_threshold_pct"] is None
    assert block["reduced_pct"] == block["default_pct"] == 10


def test_finland_is_tiered_five_and_fifteen():
    """Финляндия — 5 % при доле от 10 %, иначе 15 %."""
    block = rates()["FI"]["dividends"]

    assert block["ownership_threshold_pct"] == 10
    assert (block["reduced_pct"], block["default_pct"]) == (5, 15)
