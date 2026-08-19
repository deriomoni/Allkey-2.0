"""Загрузка справочников 101.04 из data/rules_101_04.json.

Пока это только загрузчик с проверкой состава файла — типизированный доступ к
разделам будет в фазе 2 задания (`ZADANIE-101-04.md`). Здесь важно одно: если
файл повреждён или в нём нет нужного раздела, модуль должен упасть громко и
сразу, а не посчитать налог по половине справочника.

МРП и МЗП в этом файле НЕТ намеренно — они живут в `app/personnel/rates.py`.
Пороги заданы в МРП и переводятся в тенге на дату расчёта (`mrp_to_kzt`).
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

DATA_FILE = Path(__file__).with_name("data") / "rules_101_04.json"
# Названия стран и список валют — данные представления, а не нормы. Лежат
# отдельно, чтобы правки интерфейса не разводили мастер-копию справочника правил.
NAMES_FILE = Path(__file__).with_name("data") / "country_names.json"

# Разделы, без которых расчёт невозможен. Список сверен с фазой 2 задания.
REQUIRED_SECTIONS = (
    "meta",
    "constants",
    "kpn_rates",
    "service_kinds",
    "vat_place_rules",
    "vat_exemptions_454_3",
    "income_codes",
    "offshore_list",
    "treaty_codes",
    "conventions",
    "eaeu_countries",
    "deadlines",
    "penalties",
    "flags",
)


class RulesError(RuntimeError):
    """Справочник не загрузился или не той формы — считать нельзя."""


@lru_cache(maxsize=1)
def get_rules() -> dict[str, Any]:
    """Справочники 101.04. Кэшируются: файл читается один раз за процесс."""
    try:
        raw = DATA_FILE.read_text(encoding="utf-8")
    except OSError as e:
        raise RulesError(f"Не найден справочник правил {DATA_FILE}: {e}") from e

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RulesError(f"Справочник правил повреждён ({DATA_FILE}): {e}") from e

    missing = [s for s in REQUIRED_SECTIONS if s not in doc]
    if missing:
        raise RulesError(f"В справочнике правил нет разделов: {', '.join(missing)}")

    version = doc["meta"].get("rules_version")
    if not version:
        raise RulesError("В справочнике правил не указан meta.rules_version")

    forbidden = [k for k in ("mrp_2026", "mzp_2026") if k in doc["constants"]]
    if forbidden:
        raise RulesError(
            "В constants вернулись МРП/МЗП: "
            f"{', '.join(forbidden)}. Единственный источник — app/personnel/rates.py"
        )

    return doc


def rules_version() -> str:
    return get_rules()["meta"]["rules_version"]


def mrp_to_kzt(threshold_mrp: int, on: Optional[date] = None) -> int:
    """Порог в МРП → тенге по МРП, действующему на дату `on`.

    Импорт локальный: держит зависимость от модуля кадров явной и не тащит его
    при простом чтении справочника.
    """
    from app.personnel.rates import get_rates

    return threshold_mrp * get_rates(on).mrp


@lru_cache(maxsize=1)
def get_country_names() -> dict[str, Any]:
    """Русские названия стран и список валют для выпадающих списков."""
    try:
        return json.loads(NAMES_FILE.read_text(encoding="utf-8"))
    except OSError as e:
        raise RulesError(f"Не найден справочник названий стран {NAMES_FILE}: {e}") from e
    except json.JSONDecodeError as e:
        raise RulesError(f"Справочник названий стран повреждён: {e}") from e


def country_options() -> list[dict[str, Any]]:
    """Варианты для вопроса S2.3 — страна резидентства контрагента.

    Налоговые признаки считаются здесь, а не в интерфейсе: офшор из перечня
    № 492, наличие конвенции и членство в ЕАЭС — это нормы, и фронтенд не должен
    знать, какая страна к чему относится. Ключ офшорной записи — `OFF<номер>`:
    ISO-кода у них нет, а в графу D всё равно идёт порядковый номер (R-FORM-01).
    """
    rules = get_rules()
    names = get_country_names()["names"]
    conventions = set(rules["conventions"]["countries"])
    eaeu = set(rules["eaeu_countries"])

    options = [
        {
            "key": iso,
            "name": name,
            "iso": iso,
            "is_offshore": False,
            "offshore_no": None,
            "has_convention": iso in conventions,
            "is_eaeu": iso in eaeu,
        }
        for iso, name in sorted(names.items(), key=lambda kv: kv[1])
    ]
    options += [
        {
            "key": f"OFF{entry['no']}",
            "name": entry["name"],
            "iso": None,
            "is_offshore": True,
            "offshore_no": entry["no"],
            "has_convention": False,
            "is_eaeu": False,
        }
        for entry in rules["offshore_list"]["list"]
    ]
    return options
