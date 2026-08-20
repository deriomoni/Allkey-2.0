"""Объяснение вердикта: что применилось, что нет и откуда взялись числа.

Блок 2 экрана результата (ТЗ §6). Слой лежит НАД движком и ничего не решает
сам: тексты берутся из раздела `decisions` справочника, а исходы — из журнала
`verdict.decisions`, который движок пишет в точках принятия решений. Поэтому
объяснение не может разойтись с расчётом: оно описывает исполненный код,
а не предикаты, вычисленные заново.

Налоговых формулировок здесь нет — только подстановка и форматирование.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

NBSP = " "

# Развилки, у которых есть альтернатива, и как её получить: какой ответ
# заменить и на что. Ключи совпадают с номерами правил в справочнике.
COUNTERFACTUAL_FLIPS: dict[str, dict[str, Any]] = {
    # Условие записи — «при наличии корректного сертификата», а корректность
    # это два ответа: сертификат есть и он соответствует ст. 702.
    "R-CONV-05": {"S7.2": "yes", "S7.3": "yes"},
    "R-CONV-04": {"S7.5": "yes"},
    "R-KPN-16": {"S5.4": "yes"},
    "R-REP-02": {"S2.5": "УНК (условный)"},
    # R-CONV-08 — доля участия: подставляется порог конкретной конвенции,
    # он известен только в момент построения, поэтому обрабатывается отдельно.
    "R-CONV-08": {},
}


ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}

# Подписи значений для двух плейсхолдеров текстов справочника — {event}
# и {recipient_type}. Только эти два: остальные значения интерфейс подписывает
# сам своими списками вариантов, и заводить их копию здесь незачем.
ANSWER_VALUE_LABELS: dict[str, dict[str, str]] = {
    "S2.1": {
        "payment": "перечисление денег",
        "advance": "предоплата (аванс)",
        "offset": "зачёт встречных требований",
        "in_kind": "передача имущества",
    },
    "S2.2": {
        "legal_entity": "юридическое лицо-нерезидент",
        "individual": "физическое лицо-нерезидент",
        "branch_kz": "филиал или представительство в РК",
        "ip": "индивидуальный предприниматель-нерезидент",
    },
}


@dataclass
class Input:
    """Ответ пользователя, на котором держится развилка.

    Текст самого вопроса сюда не кладётся: он живёт в визарде, который его
    рисует, и второго источника формулировок заводить не нужно. Здесь ключ,
    сырое значение и то, как значение показать.
    """
    key: str
    value: Any
    display: str


@dataclass
class Counterfactual:
    """Что было бы при другом ответе.

    Показывается только если сумма изменилась: альтернатива, не меняющая
    ни тенге, — это шум, который к третьему экрану перестают читать.
    """
    condition: str
    kpn_amount_kzt: Optional[int]
    vat_amount_kzt: Optional[int]
    delta_kzt: int
    display: str


@dataclass
class Decision:
    """Одна пройденная развилка с текстом из справочника."""
    rule_id: str
    subject: str
    applied: bool
    text: str
    norms: list[str] = field(default_factory=list)
    inputs: list[Input] = field(default_factory=list)
    note: Optional[str] = None
    counterfactual: Optional[Counterfactual] = None


# Короткие подписи видов дохода — РЯДОМ с официальным наименованием из
# приложения 5, никогда вместо него. Полный текст должен совпадать с тем,
# что бухгалтер увидит в СОНО; короткий нужен, чтобы строку можно было
# прочесть глазом, не разбирая полторы строки про паевые фонды.
INCOME_SHORT_LABELS: dict[str, str] = {
    "goods": "товары",
    "services": "работы и услуги",
    "royalty": "роялти",
    "dividends": "дивиденды",
    "interest": "вознаграждение",
    "rent": "аренда",
    "transport_intl": "международная перевозка",
    "insurance": "страховая премия",
    "capital_gain": "прирост стоимости",
    "penalty": "неустойка",
}


@dataclass
class CalcLine:
    """Строка расчёта: как из ответов получилось число."""
    label: str
    formula: str
    value: Optional[str]
    value_kzt: Optional[int] = None


@dataclass
class Explanation:
    applied: list[Decision] = field(default_factory=list)
    not_applied: list[Decision] = field(default_factory=list)
    calc: list[CalcLine] = field(default_factory=list)
    # Короткое название вида дохода для заголовка блока. Официальное
    # наименование остаётся внутри текста развилки и не подменяется.
    income_short: Optional[str] = None

    @property
    def decisions(self) -> list[Decision]:
        return self.applied + self.not_applied


# ── Форматирование ─────────────────────────────────────────────────────────

def money(value: Optional[int | Decimal | float]) -> str:
    """Тенге с неразрывными пробелами между разрядами."""
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", NBSP)


def percent(rate: Optional[float]) -> str:
    """Ставка из доли: 0.15 → «15 %». Дробные до целого не округляем."""
    if rate is None:
        return "—"
    pct = Decimal(str(rate)) * 100
    text = f"{pct.normalize():f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')}{NBSP}%"


def _display(key: str, value: Any, refbooks: dict) -> str:
    if value is None or value == "":
        return "не указано"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    labels = ANSWER_VALUE_LABELS.get(key) or {}
    if isinstance(value, str) and value in labels:
        return labels[value]
    if key == "S1.1" and isinstance(value, dict) and value.get("quarter"):
        quarter = ROMAN.get(value["quarter"], value["quarter"])
        return f"{quarter} квартал {value.get('year', '')} года".strip()
    if isinstance(value, dict):
        parts = [f"{name}: {_display(name, item, refbooks)}"
                 for name, item in value.items() if item not in (None, "")]
        return ", ".join(parts) if parts else "не указано"
    if value in ("yes", "no"):
        return "да" if value == "yes" else "нет"

    # Справочники в rules.json хранятся то списком записей, то словарём —
    # обходим обе формы, чтобы подпись не зависела от формы хранения.
    for section in ("income_codes", "service_kinds"):
        rows = refbooks.get(section) or []
        if isinstance(rows, dict):
            rows = rows.get("list") or list(rows.values())
        for row in rows:
            if isinstance(row, dict) and row.get("id") == value:
                return row.get("label") or str(value)
    return str(value)


# ── Сборка ─────────────────────────────────────────────────────────────────

def explain(answers: dict, refbooks: dict, verdict, as_of_date: date,
            usd_rate: Optional[float] = None) -> Explanation:
    """Объяснение вердикта. Чистая функция, как и сам движок."""
    records = refbooks.get("decisions") or {}
    result = Explanation(calc=_calc_lines(answers, verdict),
                         income_short=INCOME_SHORT_LABELS.get(answers.get("S5.1")))
    values = _placeholder_values(answers, refbooks, verdict)

    for rule_id, applied in verdict.decisions.items():
        record = records.get(rule_id)
        if record is None:
            # Развилка есть в коде, а текста для неё нет. Молчать нельзя:
            # пользователь увидит дыру в трассировке и не поймёт, чего не
            # хватает. Показываем номер — этого достаточно, чтобы завести текст.
            record = {"subject": rule_id, "norms": [], "fork": [],
                      "applied": "решение принято, текст не заведён",
                      "not_applied": "решение принято, текст не заведён"}

        decision = Decision(
            rule_id=rule_id,
            subject=_fill(record["subject"], values),
            applied=applied,
            text=_fill(record["applied" if applied else "not_applied"], values),
            norms=list(record.get("norms") or []),
            inputs=[Input(key=key, value=answers.get(key),
                          display=_display(key, answers.get(key), refbooks))
                    for key in record.get("fork") or []],
            note=record.get("note"),
        )
        if not applied and record.get("counterfactual"):
            decision.counterfactual = _counterfactual(
                rule_id, record["counterfactual"], values,
                answers, refbooks, verdict, as_of_date, usd_rate)

        (result.applied if applied else result.not_applied).append(decision)

    return result


VOWELS = "аеёиоуыэюя"


def _fill(text: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        if name == "country":
            text = _fill_country(text, value)
            continue
        text = text.replace("{" + name + "}", value)
    return text


def _fill_country(text: str, country: str) -> str:
    """Подставить страну и, если нужно, поправить предлог на «со».

    Тексты справочника написаны с предлогом «с»: «Конвенция с {country}».
    Перед «Словенией», «Швейцарией», «Швецией», «Словакией» нормативная форма —
    «со»: сочетание с/з/ш/ж плюс согласная. Это исправление грамматики, а не
    правка формулировки владельца, и делать его в самом справочнике нельзя:
    предлог там один на все 55 стран. Аббревиатуры исключены — «с США», а не
    «со США».
    """
    needs_so = (
        len(country) > 1
        and country[0].lower() in "сзшж"
        and country[1].lower() not in VOWELS
        and not country.isupper()
    )
    if needs_so:
        text = text.replace("с {country}", "со {country}")
    return text.replace("{country}", country)


def _placeholder_values(answers: dict, refbooks: dict, verdict) -> dict[str, str]:
    """Шестнадцать плейсхолдеров из `decisions._placeholders`. Других нет."""
    period = answers.get("S1.1") or {}
    share = answers.get("S5.8") or {}

    return {
        "country": _country_name(answers.get("S2.3"), refbooks),
        "share_pct": _plain(share.get("share_pct")),
        "threshold_pct": _plain(_treaty_threshold(answers, refbooks)),
        "rate": percent(verdict.kpn.rate),
        "rate_alt": percent(verdict.kpn.position_rate),
        "amount": money(verdict.kpn.amount_kzt),
        "amount_alt": "—",
        "delta": "—",
        "unk": str(answers.get("S2.5") or "не указан"),
        "income_type": _income_label(verdict.graphs.get("F"), refbooks),
        "income_code": str(verdict.graphs.get("F") or "—"),
        "recipient_type": _display("S2.2", answers.get("S2.2"), refbooks),
        "event": _display("S2.1", answers.get("S2.1"), refbooks),
        # Квартал римскими: так он записан в форме и так же выглядит
        # в строке «из ответов» — одна операция не должна выглядеть
        # как две разных в двух строках одного абзаца.
        "quarter": ROMAN.get(period.get("quarter"), str(period.get("quarter") or "—")),
        "year": str(period.get("year") or "—"),
        "currency": str(answers.get("S1.5") or "KZT"),
    }


def _income_label(code: Optional[str], refbooks: dict) -> str:
    """Официальное наименование вида дохода по коду из приложения 5."""
    rows = (refbooks.get("income_codes") or {}).get("list") or []
    for row in rows:
        if row.get("code") == str(code):
            return row.get("label") or str(code)
    return str(code or "—")


def _plain(value) -> str:
    """Число по-русски: разряды неразрывным пробелом, дробная часть запятой."""
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return str(value)
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return f"{int(number):,}".replace(",", NBSP)
    return f"{number:,.2f}".replace(",", NBSP).replace(".", ",")


def _rate(value) -> str:
    """Курс всегда с копейками: 591 и 591,00 в одной колонке читаются как
    разные величины, хотя это одно и то же число."""
    if value is None:
        return "—"
    return f"{Decimal(str(value)):,.2f}".replace(",", NBSP).replace(".", ",")


def _country_name(iso: Optional[str], refbooks: dict) -> str:
    """Название страны для текста. Имена — презентационные, они лежат
    отдельно от мастер-справочника, чтобы правки в интерфейсе его не трогали."""
    from app.f10104.rules import get_country_names  # noqa: PLC0415

    data = get_country_names() or {}
    # Тексты справочника ставят страну в творительный падеж («Конвенция
    # с {country}»), поэтому подставляем готовую форму. Именительный —
    # запасной вариант, лучше «с Германия», чем пустое место.
    forms = data.get("instrumental") or {}
    names = data.get("names") or {}
    return forms.get(iso or "") or names.get(iso or "") or (iso or "—")


def _treaty_threshold(answers: dict, refbooks: dict):
    """Порог доли участия ПО КОНВЕНЦИИ (R-CONV-08), не по кодексу."""
    iso = answers.get("S2.3")
    record = ((refbooks.get("conventions") or {}).get("rates") or {}).get(iso or "")
    block = (record or {}).get("dividends") or {}
    return block.get("ownership_threshold_pct")


# ── Альтернатива ───────────────────────────────────────────────────────────

def _counterfactual(rule_id: str, condition: str, values: dict[str, str],
                    answers: dict, refbooks: dict, verdict,
                    as_of_date: date, usd_rate) -> Optional[Counterfactual]:
    """Пересчёт при другом ответе. Возвращает None, если сумма не изменилась.

    Второе условие владельца: альтернатива показывается, только если она
    меняет сумму. Одинаковые числа рядом читаются как ошибка расчёта.
    """
    from app.f10104.engine import EngineError, evaluate  # noqa: PLC0415

    flip = dict(COUNTERFACTUAL_FLIPS.get(rule_id) or {})
    if rule_id == "R-CONV-08":
        threshold = _treaty_threshold(answers, refbooks)
        if threshold is None:
            return None
        share = dict(answers.get("S5.8") or {})
        share["share_pct"] = threshold
        flip = {"S5.8": share}
    if not flip:
        return None

    alternative = deepcopy(answers)
    alternative.update(flip)
    try:
        other = evaluate(alternative, refbooks=refbooks, as_of_date=as_of_date,
                         usd_rate=usd_rate)
    except EngineError:
        # Альтернатива требует ответов, которых нет. Домысливать их — значит
        # показать сумму по анкете, которую пользователь не заполнял.
        return None

    now = (verdict.kpn.amount_kzt or 0) + (verdict.vat.amount_kzt or 0)
    then = (other.kpn.amount_kzt or 0) + (other.vat.amount_kzt or 0)
    if now == then:
        return None

    delta = then - now
    direction = "меньше" if delta < 0 else "больше"
    return Counterfactual(
        condition=_fill(condition, values),
        kpn_amount_kzt=other.kpn.amount_kzt,
        vat_amount_kzt=other.vat.amount_kzt,
        delta_kzt=delta,
        display=f"{money(then)}{NBSP}₸ — на {money(abs(delta))}{NBSP}₸ {direction}",
    )


# ── Расчёт ─────────────────────────────────────────────────────────────────

def _calc_lines(answers: dict, verdict) -> list[CalcLine]:
    """Как из ответов получились числа. Пустые обязательства не расписываем."""
    lines: list[CalcLine] = []
    currency = answers.get("S1.5") or "KZT"
    amount = answers.get("S4.4")
    fx = verdict.fx_used or {}
    in_currency = currency != "KZT"

    if amount is not None:
        lines.append(CalcLine(label="Сумма по договору", formula="",
                              value=f"{_plain(amount)}{NBSP}{currency}"))

    if in_currency:
        for key, label in (("kpn", "Курс на дату базы КПН"),
                           ("vat", "Курс на дату оборота")):
            if fx.get(key):
                lines.append(CalcLine(label=label, formula="официальный курс НБ РК",
                                      value=_rate(fx[key])))

    if verdict.kpn.applicable is not False and verdict.kpn.base_kzt:
        lines.append(CalcLine(
            label="База КПН",
            formula=(f"{_plain(amount)}{NBSP}{currency} × {_plain(fx.get('kpn'))}"
                     if in_currency else "сумма договора"),
            value=f"{money(verdict.kpn.base_kzt)}{NBSP}₸",
            value_kzt=verdict.kpn.base_kzt))
        if verdict.kpn.rate is not None:
            lines.append(CalcLine(
                label="КПН у источника выплаты",
                formula=f"{money(verdict.kpn.base_kzt)}{NBSP}₸ × "
                        f"{percent(verdict.kpn.rate)}",
                value=f"{money(verdict.kpn.amount_kzt)}{NBSP}₸",
                value_kzt=verdict.kpn.amount_kzt))

    if verdict.vat.applicable and verdict.vat.base_kzt:
        lines.append(CalcLine(
            label="База НДС за нерезидента", formula="оборот по приобретению",
            value=f"{money(verdict.vat.base_kzt)}{NBSP}₸",
            value_kzt=verdict.vat.base_kzt))
        lines.append(CalcLine(
            label="НДС за нерезидента",
            formula=f"{money(verdict.vat.base_kzt)}{NBSP}₸ × "
                    f"{percent(verdict.vat.rate)}",
            value=f"{money(verdict.vat.amount_kzt)}{NBSP}₸",
            value_kzt=verdict.vat.amount_kzt))

    return lines
