"""Движок помогайки по форме 101.04 — детерминированный расчёт.

`evaluate(answers, refbooks, as_of_date) -> Verdict` — чистая функция: без
побочных эффектов, без сети, без обращений к модели. Один и тот же вход всегда
даёт один и тот же выход, иначе налоговый вывод нельзя воспроизвести через год.

Ни одна ставка, код вида дохода и список стран здесь не зашиты: всё читается из
`data/rules_101_04.json`. МРП и МЗП — из `app/personnel/rates.py`, второго
источника истины по ним нет.

Правила пронумерованы как в ТЗ §5 и §8 (`docs/tax/101-04/tz-pomogayki.md`):
R-ROUTE, R-KPN, R-CONV, R-VAT, R-REP, R-FORM. Номер правила указан в коде рядом
с реализацией, чтобы правку нормы можно было донести до нужной строки.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from app.f10104.dates import resolve as resolve_date_rule
from app.f10104.rules import mrp_to_kzt

# ── Значения ответов, на которые опирается движок ──────────────────────────
# Словарь совпадает с `tests/answers.py`; он же документирован там.

GOODS, SERVICES, ROYALTY, DIVIDENDS = "goods", "services", "royalty", "dividends"
INTEREST, RENT, TRANSPORT_INTL = "interest", "rent", "transport_intl"
INSURANCE, CAPITAL_GAIN, PENALTY = "insurance", "capital_gain", "penalty"

IN_KZ, OUTSIDE_KZ, PARTLY = "kz", "outside", "partly"

ROUTE_FORM = "form_101_04"
ROUTE_INDIVIDUAL = "individual_200_00"
ROUTE_PE_BRANCH = "pe_branch_not_reported"
ROUTE_OUT_OF_SCOPE = "out_of_scope"

# Вид дохода → ключ раздела out_of_scope в справочнике.
#
# Помогайка считает там, где вывод следует из анкеты. Где он зависит от
# первичных документов или квалификации отношений — не считает и не гадает,
# а показывает выход. Один уверенный неверный ответ обесценивает сто верных.
#
# Вариант из списка при этом НЕ УБИРАЕТСЯ: не нашедший своего случая выберет
# соседний и получит уверенный неверный ответ — это хуже честного отказа.
OUT_OF_SCOPE_INCOME = {
    GOODS: "goods",              # четыре развилки, каждая переворачивает ответ
    "agency": "agency",          # зависит от обоснованности отчёта агента
    "inbound_aid": "inbound_aid",  # доход у резидента, форма 100.00
}

CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_LIKELY = "likely"
CONFIDENCE_MANUAL = "manual_review"

FIRST_SUPPORTED_YEAR = 2026          # R-ROUTE-01: старый кодекс не поддерживаем
ADVANCE_CONTROL_MONTHS = 12          # ст. 679 п. 1 пп. 5)
KPN_PAYMENT_DAYS_AFTER_MONTH = 25    # ст. 684 п. 1 пп. 1)
IPN_TRANSFER_DAY = 25                # ст. 692 п. 6 — 25 число СЛЕДУЮЩЕГО месяца
MONTH_ROMAN = {1: "I", 2: "II", 3: "III"}

# Соответствие «тип дохода → код графы F» и «вид услуги → код». Перенесено из
# прототипа (функция incomeCode), сами коды — из справочника income_codes.
INCOME_CODE_BY_TYPE = {
    ROYALTY: "1130", DIVIDENDS: "1100", INTEREST: "1120", RENT: "1140",
    TRANSPORT_INTL: "1170", INSURANCE: "1161", CAPITAL_GAIN: "1062",
    PENALTY: "1090",
}
INCOME_CODE_BY_SERVICE_ABROAD = {
    "management": "1030", "financial": "1032", "consulting": "1033",
    "engineering": "1034", "marketing": "1035", "audit": "1036",
    "legal": "1037", "info_processing": "1038", "design": "1039",
    "advertising": "1041",
}
CODE_SERVICES_IN_KZ = "1020"
CODE_SERVICES_ABROAD_OTHER = "1031"
CODE_GOODS_SUPPLY = "1011"
CODE_OFFSHORE = "1040"
CODE_OTHER = "1340"

# Типы дохода, для которых конвенция даёт пониженную ставку (ст. 706), а не
# полное освобождение (ст. 705).
REDUCED_RATE_INCOME = {DIVIDENDS, ROYALTY, INTEREST}


class EngineError(RuntimeError):
    """Расчёт невозможен: не хватает ответа или справочные данные не сходятся."""


# ── Результат ──────────────────────────────────────────────────────────────

@dataclass
class KpnObligation:
    taxable: bool = False
    # None — ставка не определена по существу (уровень обязательства из
    # disclaimer.manual_review_policy). Цифры быть не должно: ни суммы, ни ставки.
    rate: Optional[float] = 0.0
    # None — вывода по существу нет (уровень обязательства из
    # disclaimer.manual_review_policy). Цифры не показываются ни в каком виде.
    applicable: Optional[bool] = True
    rate_undetermined: bool = False
    treaty_note: Optional[str] = None
    # Позиции по спорной норме: показываются вместо ставки.
    positions: list[dict] = field(default_factory=list)
    what_to_check: Optional[str] = None
    money_at_stake: Optional[str] = None
    # Позиция по спорной норме, выбранная ПОЛЬЗОВАТЕЛЕМ под его обоснование.
    # Помогайка этот вывод себе не присваивает — в результате и в печати идёт
    # отдельная строка о том, кто принял решение.
    position_chosen: Optional[str] = None
    position_basis: Optional[str] = None
    position_rate: Optional[float] = None
    progressive: Optional[dict] = None
    base_kzt: int = 0
    amount_kzt: int = 0
    convention_applied: bool = False
    convention_type: Optional[str] = None      # "full" | "reduced"
    needs_manual_treaty_rate: bool = False
    basis: list[str] = field(default_factory=list)


@dataclass
class VatObligation:
    applicable: Optional[bool] = None          # None == manual_review
    rate: float = 0.0
    base_kzt: int = 0
    amount_kzt: int = 0
    place_of_supply: Optional[str] = None
    reason: str = ""
    basis: str = ""


@dataclass
class Periods:
    kpn_quarter: Optional[int] = None
    kpn_year: Optional[int] = None
    vat_quarter: Optional[int] = None
    vat_year: Optional[int] = None


@dataclass
class Deadlines:
    kpn_payment: Optional[date] = None
    vat_payment: Optional[date] = None
    form_101_04: Optional[date] = None
    ipn_payment: Optional[date] = None


@dataclass
class Reporting:
    form_101_04_required: bool = False
    reported_in_form: bool = False
    threshold_applied: bool = False
    threshold_checked: bool = True
    period: Optional[str] = None


@dataclass
class IndividualRoute:
    """Маршрут по физлицу-нерезиденту: форма 200.00, приложение 200.02."""
    ipn_rate: float = 0.0
    opv: bool = False
    vosms: bool = False
    oosms: bool = False
    so: bool = False
    requires_iin: bool = False
    form: str = ""
    appendix: str = ""
    basis: list[str] = field(default_factory=list)


@dataclass
class FixMode:
    additional_form_required: bool = False
    penalty_relief_business_days: int = 0
    penalty_daily_rate: float = 0.0
    basis: str = ""


@dataclass
class Verdict:
    route: str = ROUTE_FORM
    confidence: str = CONFIDENCE_CONFIRMED
    rules_version: str = ""
    kpn: KpnObligation = field(default_factory=KpnObligation)
    vat: VatObligation = field(default_factory=VatObligation)
    periods: Periods = field(default_factory=Periods)
    deadlines: Deadlines = field(default_factory=Deadlines)
    reporting: Reporting = field(default_factory=Reporting)
    individual: IndividualRoute = field(default_factory=IndividualRoute)
    fix: FixMode = field(default_factory=FixMode)
    graphs: dict[str, Any] = field(default_factory=dict)
    lines: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)
    advance_control_date: Optional[date] = None
    # Ключ раздела out_of_scope справочника, если операция за периметром.
    # Пока он заполнен, сумм в вердикте нет и быть не должно.
    out_of_scope: Optional[str] = None
    # Какая норма ст. 684 п. 1 применилась, на какую дату курс и когда платить.
    # Выводится из фактов (две даты, вычеты, способ расчёта), а не из ответа
    # пользователя «аванс или нет» — см. app/f10104/dates.py.
    date_rule: Optional[Any] = None
    fx_used: dict[str, float] = field(default_factory=dict)
    # True, когда даты оборота и выплаты разные, а курс задан один: база НДС
    # посчитана по курсу выплаты, хотя ст. 463 п. 2 требует курс на дату
    # оборота. Умолчание оставлено ради совместимости, но молчать о нём нельзя.
    fx_single_rate_reused: bool = False
    # Развилки, пройденные движком: номер правила → применилось ли.
    # Порядок вставки = порядок принятия решений, он же порядок в объяснении.
    decisions: dict[str, bool] = field(default_factory=dict)
    _flag_severity: dict[str, str] = field(default_factory=dict, repr=False)

    def decide(self, rule_id: str, applied: bool) -> bool:
        """Зафиксировать пройденную развилку и вернуть её исход.

        Пишет сам движок в той точке, где решение принято. Объяснение потом
        строится по этому журналу, а не по предикатам, вычисленным заново:
        пересчитанный предикат может разойтись с кодом и объяснить не то,
        что посчитано.
        """
        self.decisions[rule_id] = applied
        return applied

    def flag_severity(self, code: str) -> Optional[str]:
        """Важность флага из справочника: info / medium / high."""
        return self._flag_severity.get(code)


@dataclass
class FormLines:
    """Строки основного расчёта по месяцам квартала (I, II, III) и итогом (IV)."""
    line_001: dict[str, int] = field(default_factory=dict)
    line_002: dict[str, int] = field(default_factory=dict)


# ── Вспомогательное ────────────────────────────────────────────────────────

def _money(value: Decimal | float) -> int:
    """Тенге целыми, округление арифметическое."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _quarter(d: Optional[date]) -> Optional[int]:
    return None if d is None else (d.month - 1) // 3 + 1


def _month_of_quarter(d: Optional[date]) -> Optional[int]:
    return None if d is None else (d.month - 1) % 3 + 1


def _end_of_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1) - _one_day()


def _one_day():
    from datetime import timedelta
    return timedelta(days=1)


def _plus_days(d: date, days: int) -> date:
    from datetime import timedelta
    return d + timedelta(days=days)


def _plus_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, _days_in_month(year, month)))


def _days_in_month(year: int, month: int) -> int:
    nxt = date(year + month // 12, month % 12 + 1, 1)
    return (nxt - _one_day()).day


def _iso(value: Optional[str]) -> Optional[date]:
    return None if not value else date.fromisoformat(value)


# ── Справочные выборки ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Country:
    key: str
    iso: Optional[str]
    is_offshore: bool
    offshore_no: Optional[int]
    has_convention: bool
    is_eaeu: bool

    @property
    def graph_d(self) -> str:
        """R-FORM-01: для офшоров — порядковый номер перечня № 492, не ISO."""
        return str(self.offshore_no) if self.is_offshore else (self.iso or "")


def _resolve_country(key: Optional[str], refbooks: dict) -> Country:
    if not key:
        raise EngineError("Не указана страна резидентства контрагента (S2.3)")

    if key.upper().startswith("OFF"):
        number = int(key[3:])
        known = {e["no"] for e in refbooks["offshore_list"]["list"]}
        if number not in known:
            raise EngineError(f"В перечне № 492 нет юрисдикции № {number}")
        # Офшор перекрывает конвенцию целиком — ст. 682 п. 2.
        return Country(key, None, True, number, False, False)

    iso = key.upper()
    return Country(
        key=key,
        iso=iso,
        is_offshore=False,
        offshore_no=None,
        has_convention=iso in refbooks["conventions"]["countries"],
        is_eaeu=iso in refbooks["eaeu_countries"],
    )


def _service_kind(kind_id: Optional[str], refbooks: dict) -> Optional[dict]:
    if not kind_id:
        return None
    for kind in refbooks["service_kinds"]:
        if kind["id"] == kind_id:
            return kind
    raise EngineError(f"В справочнике нет вида услуги «{kind_id}»")


def _kpn_rate(code: str, refbooks: dict) -> dict:
    for entry in refbooks["kpn_rates"]:
        if entry["code"] == code:
            return entry
    raise EngineError(f"В справочнике нет ставки КПН «{code}»")


# ── Код вида дохода (графа F) ──────────────────────────────────────────────

def _income_code(answers: dict, country: Country, kind: Optional[dict]) -> str:
    if country.is_offshore:
        return CODE_OFFSHORE                      # R-FORM-01 + ст. 679 п. 1 пп. 4)

    income = answers.get("S5.1")
    if income == GOODS:
        return CODE_SERVICES_IN_KZ if answers.get("S5.3") == "yes" else CODE_GOODS_SUPPLY
    if income in INCOME_CODE_BY_TYPE:
        return INCOME_CODE_BY_TYPE[income]
    if income == SERVICES:
        if answers.get("S6.1") == IN_KZ:
            return CODE_SERVICES_IN_KZ
        if kind and kind["id"] in INCOME_CODE_BY_SERVICE_ABROAD:
            return INCOME_CODE_BY_SERVICE_ABROAD[kind["id"]]
        return CODE_SERVICES_ABROAD_OTHER
    return CODE_OTHER


# ── База по КПН ────────────────────────────────────────────────────────────

def _taxable_amount_fx(answers: dict, date_rule=None) -> Decimal:
    """Сумма в валюте договора, попадающая в базу.

    Три случая, все из ТЗ:
    * товар с выделенной стоимостью работ/услуг в РК → только S5.4a (S5.4a, ст. 680 п. 1 пп. 4);
    * аванс с частичным начислением → только начисленная часть (R-KPN-19);
    * иначе — вся сумма по акту (S4.4).
    """
    # Аванс без акта (R-DATE-02): доход ещё не начислен, базы нет.
    # Прежде это приходило ярлыком S5.9.accrued = False, теперь выводится
    # из фактов — ярлык принимается только из старых черновиков.
    if date_rule is not None and date_rule.rule_id == "R-DATE-02":
        return Decimal("0")                       # R-KPN-19: дохода нет

    accrual = answers.get("S5.9") or {}
    if accrual and accrual.get("accrued") is False:
        return Decimal("0")                       # R-KPN-19: дохода нет

    # Частичное начисление НЕ спрашивается, а выводится из суммы аванса
    # и суммы по акту (R-DATE-04). Отдельный вопрос «начислена ли часть
    # суммы» был бы тем же ярлыком состояния, от которых мы ушли, а нужные
    # числа уже собраны. Прежний вход `S5.9.accrued_amount` удалён.
    if date_rule is not None and date_rule.taxable_now_fx is not None:
        return date_rule.taxable_now_fx

    if answers.get("S5.1") == GOODS and answers.get("S5.4") == "yes":
        services_amount = answers.get("S5.4a")
        if services_amount is None:
            raise EngineError(
                "Стоимость работ и услуг на территории РК выделена, но не указана (S5.4a)")
        return Decimal(str(services_amount))

    return Decimal(str(answers.get("S4.4") or 0))


# ── Основной расчёт ────────────────────────────────────────────────────────

def evaluate(answers: dict, refbooks: dict, as_of_date: date,
             usd_rate: Optional[float] = None) -> Verdict:
    """Обязательства налогового агента по одной операции.

    `answers` не изменяется. `refbooks` — загруженный `rules_101_04.json`.

    `usd_rate` — официальный курс доллара НБ РК на дату выплаты. Нужен только
    для сравнения необлагаемой суммы с порогом раскрытия 50 000 USD, когда
    договор заключён не в долларах. Курс **передаётся снаружи**, а не тянется
    из сети внутри: движок обязан оставаться чистой функцией, иначе расчёт
    перестанет быть воспроизводимым и его нельзя будет пересчитать через год
    (железное правило 3 задания). Курс добывает вызывающая сторона —
    роутер делает это через `nbrk_rates.get_official_rate("USD", дата)`.
    Если курс недоступен, порог не проверяется молча: выставляется
    `manual_review` и флаг F-THRESHOLD-FX.
    """
    v = Verdict(rules_version=refbooks["meta"]["rules_version"])
    v._flag_severity = {code: spec.get("severity", "info")
                        for code, spec in refbooks["flags"].items()}

    def flag(code: str) -> None:
        if code not in v.flags:
            v.flags.append(code)

    period = answers.get("S1.1") or {}
    payment_date = answers.get("S4.2")
    act_date = answers.get("S4.1")

    # ── R-ROUTE-01. Периметр v1 — только новый кодекс
    if int(period.get("year", 0)) < FIRST_SUPPORTED_YEAR:
        v.route = ROUTE_OUT_OF_SCOPE
        v.basis.append("Помогайка работает с НК РК от 18.07.2025 № 214-VIII, с 01.01.2026")
        return v

    # ── R-SCOPE-01. Виды дохода, по которым расчёта не будет.
    # Возврат ранний и намеренно пустой: ни базы, ни ставки, ни кода дохода,
    # ни сроков. Серая предварительная цифра здесь была бы хуже её отсутствия —
    # её запомнят, а оговорку рядом нет.
    scope_key = OUT_OF_SCOPE_INCOME.get(answers.get("S5.1"))
    if scope_key:
        v.route = ROUTE_OUT_OF_SCOPE
        v.out_of_scope = scope_key
        v.kpn = KpnObligation(taxable=False, rate=None, applicable=False)
        v.vat = VatObligation(applicable=False, reason=None, basis=None)
        v.reporting = Reporting(form_101_04_required=False, reported_in_form=False)
        return v

    # Развилки, которые на вывод не влияют, но объясняют, откуда взялись
    # период и курс. Пользователь спрашивает про них чаще, чем про ставку.
    v.decide("period", True)
    v.decide("currency", answers.get("S1.5") not in (None, "KZT"))

    country = _resolve_country(answers.get("S2.3"), refbooks)
    v.decide("offshore", country.is_offshore)
    kind = _service_kind(answers.get("S5.5"), refbooks)
    income = answers.get("S5.1")
    v.decide("income-type", income is not None)
    if income == SERVICES:
        v.decide("service-group-a",
                 bool(kind and kind.get("taxable_regardless_of_place")))

    # ── R-ROUTE-02. Физлицо — это 200.00, а не 101.04
    # Развилка «тип получателя» описывает, ЧЕЙ порядок применён, а не
    # «получатель — физлицо». Она пройдена, как только получатель назван.
    v.decide("recipient-type", bool(answers.get("S2.2")))
    if answers.get("S2.2") == "individual":
        return _individual_route(answers, refbooks, country, v, payment_date)

    # ── R-ROUTE-03/04. Постоянное учреждение
    if answers.get("S3.1") == "yes" and answers.get("S3.2") == "branch" \
            and answers.get("S3.3") == "yes":
        v.route = ROUTE_PE_BRANCH
        v.kpn.basis.append("ст. 683 п. 1 — расчёты с зарегистрированным ПУ")
        v.basis.append("КПН не удерживается, ПУ отчитывается самостоятельно")
        return v

    pe_via_head_office = answers.get("S3.1") == "yes" and (
        answers.get("S3.2") == "head_office" or answers.get("S3.3") == "no")
    if v.decide("pe-risk",
                answers.get("S3.4") in {"over_183", "construction",
                                        "dependent_agent"}):
        flag("F-PE-RISK")

    # ── Сумма и курсы
    # Три даты одной операции дают три РАЗНЫХ курса, и переиспользовать один
    # на всё нельзя (ТЗ §4, блок S4):
    #   S4.5  — курс на дату выплаты      → база КПН по выплаченным доходам;
    #   S4.5a — курс на дату начисления   → база КПН по авансу (ст. 684 п. 1 пп. 3);
    #   S4.5b — курс на дату оборота      → база НДС (ст. 463 п. 2).
    # Если отдельный курс не указан, берётся курс выплаты — поведение по
    # умолчанию не меняется.
    # ── R-DATE. Норму, дату курса и срок выводит движок по фактам.
    # Считается ДО базы: от правила зависит, начислен ли доход вообще.
    v.date_rule = date_rule = resolve_date_rule(answers)
    v.decide(date_rule.rule_id, date_rule.obligation_arisen)

    amount_fx = _taxable_amount_fx(answers, date_rule)
    payment_fx = Decimal(str(answers.get("S4.5") or 1))
    accrual_fx = Decimal(str(answers.get("S4.5a") or answers.get("S4.5") or 1))
    turnover_fx = Decimal(str(answers.get("S4.5b") or answers.get("S4.5") or 1))

    # Обязанность удержать возникает от ЛЮБОГО способа расчёта: зачёт
    # встречных требований и передача имущества — такая же выплата, как
    # перечисление денег.
    v.decide("payment-event", bool(answers.get("S2.1")))

    # Курс базы КПН берётся на ту дату, которую назвала норма. Прежнее
    # «аванс → курс начисления, иначе курс выплаты» было тем же правилом,
    # но выведенным из ответа пользователя вместо фактов.
    on_accrual = date_rule.subparagraph in ("пп. 3)", "пп. 4)", "пп. 3) + пп. 1)")
    kpn_fx = accrual_fx if on_accrual else payment_fx
    base_kzt = _money(amount_fx * kpn_fx)
    vat_base_kzt = _money(amount_fx * turnover_fx)
    if answers.get("S1.5") not in (None, "KZT"):
        flag("F-FX-BASIS")

    # ── R-KPN. Облагаемость и ставка по НК
    taxable, nk_rate, basis = _kpn_position(answers, refbooks, country, kind,
                                            income, flag, pe_via_head_office, v)
    v.kpn.taxable = taxable
    v.kpn.basis.extend(basis)
    if taxable and nk_rate is None:
        # Ставка Налогового кодекса сама по себе спорна — конвенция этого не
        # лечит: она потолок, а под потолком остаются обе позиции.
        disputed = _kpn_rate("dividends_25", refbooks)
        v.kpn.applicable = None
        v.kpn.rate_undetermined = True
        v.kpn.positions = disputed.get("positions", [])
        v.kpn.what_to_check = disputed.get("what_to_check")
        v.kpn.money_at_stake = disputed.get("money_at_stake")
    v.kpn.base_kzt = base_kzt if taxable else 0

    # ── R-CONV. Конвенция
    final_rate = nk_rate
    if taxable and nk_rate is not None:
        final_rate = _apply_convention(answers, refbooks, country, income,
                                       nk_rate, v, flag, as_of_date)
    v.kpn.rate = final_rate
    v.kpn.amount_kzt = _kpn_amount(v, final_rate, taxable)

    dates_differ = bool(act_date and payment_date and act_date != payment_date)
    v.fx_single_rate_reused = bool(
        answers.get("S1.5") not in (None, "KZT")
        and dates_differ
        and not answers.get("S4.5b")
    )

    if v.fx_single_rate_reused:
        # Текст — из справочника (F-FX-ONE-RATE, engine_field указывает сюда).
        # Умолчание не отменяем: курс на обе даты может совпадать, и на выходных
        # это буквально норма. Но молчать о подстановке нельзя.
        flag("F-FX-ONE-RATE")

    v.fx_used = {
        "kpn": float(kpn_fx),
        "vat": float(turnover_fx),
        "payment_date": float(payment_fx),
        "accrual_date": float(accrual_fx),
        "turnover_date": float(turnover_fx),
    }

    # ── R-VAT
    _apply_vat(answers, refbooks, country, kind, income, vat_base_kzt, v, flag)

    # Срок ставит правило R-DATE — ДО расчёта периодов, иначе запасной
    # вариант внутри посчитает свой и будет тут же перезаписан. Порядок
    # тут не косметика: перезапись прячет, какой из двух источников сработал.
    if date_rule.deadline:
        v.deadlines.kpn_payment = date_rule.deadline

    # ── Периоды и сроки
    _apply_periods_and_deadlines(answers, refbooks, payment_date, act_date, v, flag)

    # ── Норма даты: обоснование и контрольная дата из правила R-DATE
    v.kpn.basis.extend(date_rule.norms)
    v.kpn.basis.append(date_rule.explanation)
    if date_rule.rule_id in ("R-DATE-02", "R-DATE-03", "R-DATE-04"):
        flag("F-ADVANCE")
    # advance_control_date — это НЕ «вернуться, когда подпишут акт».
    # Это дата из F-ADVANCE: через 12 месяцев неотработанный аванс становится
    # доходом нерезидента (ст. 679 п. 1 пп. 5) независимо от конвенции.
    # Контрольная дата самого правила R-DATE живёт в date_rule.control_date
    # и означает другое — их нельзя сливать в одно поле.
    if date_rule.rule_id in ("R-DATE-02", "R-DATE-04") and payment_date:
        v.advance_control_date = _plus_months(payment_date, ADVANCE_CONTROL_MONTHS)

    # ── R-REP. Отчётность
    _apply_reporting(answers, refbooks, v, flag, usd_rate)

    # ── Графы и строки формы
    _fill_graphs(answers, refbooks, country, kind, v)

    # ── Режим исправления
    if answers.get("mode") == "fix":
        penalty = refbooks["penalties"]["penalty_interest"]
        v.fix = FixMode(
            additional_form_required=True,
            penalty_relief_business_days=3,
            penalty_daily_rate=penalty["daily_rate_at_1675"],
            basis=refbooks["penalties"]["koap_279_1"]["relief"],
        )

    # ── Уровень уверенности
    v.confidence = _confidence(v)
    return v


# ── R-KPN ──────────────────────────────────────────────────────────────────

def _kpn_position(answers, refbooks, country, kind, income, flag,
                  pe_via_head_office, v) -> tuple[bool, Optional[float], list[str]]:
    """Облагаемость и ставка по Налоговому кодексу, без учёта конвенции."""
    basis: list[str] = []

    # R-KPN-01. Офшор перекрывает всё: ставка независимо от места оказания.
    if country.is_offshore:
        flag("F-OFFSHORE")
        rate = _kpn_rate("offshore", refbooks)
        basis += ["ст. 679 п. 1 пп. 4) — доход лица из государства с льготным "
                  "налогообложением", f"{rate['basis']} — ставка {rate['rate']:.0%}"]
        return True, rate["rate"], basis

    # R-ROUTE-04. ПУ через головной офис — 20 % без вычетов.
    if pe_via_head_office:
        rate = _kpn_rate("general", refbooks)
        basis.append("ст. 690 — доход нерезидента, действующего через ПУ, без вычетов")
        return True, rate["rate"], basis

    if income == GOODS:
        # R-KPN-02. Поставка сама по себе не образует дохода из источников в РК.
        if answers.get("S5.3") != "yes":
            basis.append("ст. 680 п. 1 пп. 4) — не доход из источников в РК")
            return False, 0.0, basis
        if not v.decide("R-KPN-16", answers.get("S5.4") != "no"):
            flag("F-MIXED")
            basis.append("ст. 683 п. 8 — распределение не подтверждено, "
                         "облагается совокупная сумма")
        rate = _kpn_rate("general", refbooks)
        basis.append("ст. 679 п. 1 пп. 2) — работы и услуги на территории РК")
        return True, rate["rate"], basis

    if income == SERVICES:
        place = answers.get("S6.1")
        if kind and kind["id"] == "software_dev":
            flag("F-DESIGN-SCOPE")
        if place == IN_KZ:
            rate = _kpn_rate("general", refbooks)
            basis.append("ст. 679 п. 1 пп. 2) — услуги на территории РК")
            return True, rate["rate"], basis
        if place == PARTLY:
            if answers.get("S6.2") == "no":
                flag("F-MIXED")
            rate = _kpn_rate("general", refbooks)
            basis.append("ст. 683 п. 8 — смешанное место оказания")
            return True, rate["rate"], basis
        # Место оказания — за пределами РК.
        if kind and kind.get("taxable_regardless_of_place"):
            # R-KPN-04. Закрытый перечень: облагается несмотря на место.
            rate = _kpn_rate("general", refbooks)
            basis.append("ст. 679 п. 1 пп. 3) — услуги из закрытого перечня, "
                         "облагаются независимо от места оказания")
            return True, rate["rate"], basis
        # R-KPN-05.
        basis.append("ст. 681 п. 1 пп. 5) — работы и услуги за пределами РК")
        return False, 0.0, basis

    if income == ROYALTY:
        # R-KPN-17. Невыделенная техподдержка облагается как роялти целиком.
        if v.decide("royalty-support",
                    answers.get("S5.6") == "yes" and answers.get("S5.7") == "no"):
            flag("F-ROYALTY")
            basis.append("ст. 683 п. 5 — техподдержка не выделена, вся сумма как роялти")
        rate = _kpn_rate("royalty", refbooks)
        basis.append(f"{rate['basis']} — роялти")
        return True, rate["rate"], basis

    if income == DIVIDENDS:
        threshold = refbooks["constants"].get("dividend_reduced_ownership_pct", 25)
        share = (answers.get("S5.8") or {}).get("share_pct")
        if share is not None and share >= threshold:
            # R-KPN-08 (редакция 1.5.0). Подпункт 5) прямо исключает доходы
            # подпунктов 6)–7), а подпункт 6) относится ровно к этому случаю.
            # Буквальное чтение и официальный разбор расходятся, поэтому ставку
            # не выбираем: отдаём обе позиции и вопрос.
            rate = _kpn_rate("dividends_25", refbooks)
            resolution = rate.get("user_resolution") or {}
            answer = answers.get("S5.8") or {}
            chosen = answer.get("position")
            reason = (answer.get("position_basis") or "").strip()

            if chosen and reason:
                position = next(
                    (p for p in rate["positions"] if p["id"] == chosen), None)
                if position is None:
                    raise EngineError(
                        f"Неизвестная позиция по спорной ставке: «{chosen}». "
                        f"Допустимые: {', '.join(resolution.get('values', []))}")
                flag("F-DIV-25-RESOLVED")
                v.kpn.position_chosen = chosen
                v.kpn.position_basis = reason
                v.kpn.position_rate = position["rate"]
                v.kpn.progressive = position.get("progressive")
                basis.append(
                    f"{position['basis']} — позицию по спорной норме выбрал "
                    f"пользователь, основание: {reason}")
                return True, position["rate"], basis

            if chosen and not reason:
                # Выбор без обоснования не принимается — молча проглотить его
                # значит дать способ получить нужное число одним кликом.
                basis.append(
                    "Позиция по спорной норме выбрана, но обоснование не "
                    "заполнено — выбор не принят")

            flag("F-DIV-25")
            basis.append(f"{rate['basis']} — дивиденды при доле участия "
                         f"{threshold} % и выше, ставка спорна")
            return True, None, basis

        rate = _kpn_rate("dividends", refbooks)
        basis.append(f"{rate['basis']} — дивиденды")
        return True, rate["rate"], basis

    if income == INTEREST:
        rate = _kpn_rate("interest_loan", refbooks)
        basis.append(f"{rate['basis']} — вознаграждения по кредитам и долговым ЦБ")
        return True, rate["rate"], basis

    if income == RENT:
        rate = _kpn_rate("general", refbooks)
        basis.append("ст. 679 п. 1 пп. 16) — сдача имущества в имущественный наём")
        return True, rate["rate"], basis

    if income == TRANSPORT_INTL:
        rate = _kpn_rate("intl_transport", refbooks)
        basis.append(f"{rate['basis']} — международная перевозка")
        return True, rate["rate"], basis

    if income == INSURANCE:
        code = "reinsurance" if answers.get("S5.10") == "reinsurance" else "insurance"
        rate = _kpn_rate(code, refbooks)
        basis.append(f"{rate['basis']} — {rate['label'].lower()}")
        return True, rate["rate"], basis

    if income == CAPITAL_GAIN:
        rate = _kpn_rate("capital_gain", refbooks)
        basis.append(f"{rate['basis']} — прирост стоимости, порядок ст. 687")
        return True, rate["rate"], basis

    if income == PENALTY:
        rate = _kpn_rate("general", refbooks)
        basis.append("ст. 679 п. 1 пп. 11) — неустойка, штраф, пеня")
        return True, rate["rate"], basis

    rate = _kpn_rate("general", refbooks)
    basis.append("ст. 679 п. 1 — прочий доход из источников в РК")
    return True, rate["rate"], basis


def _kpn_amount(v: Verdict, final_rate, taxable: bool) -> int:
    """Сумма налога. Прогрессия применяется, только если она задана позицией.

    Подпункт 6) п. 1 ст. 682: 5 % в пределах 230 000 МРП, свыше — налог
    с 230 000 МРП плюс 15 % с превышения. Порог в МРП, не в тенге: при смене
    МРП он пересчитывается сам.
    """
    if not taxable or final_rate is None:
        return 0

    base = Decimal(str(v.kpn.base_kzt))
    progressive = v.kpn.progressive
    if not progressive:
        return _money(base * Decimal(str(final_rate)))

    threshold = Decimal(str(mrp_to_kzt(progressive["threshold_mrp"])))
    if base <= threshold:
        return _money(base * Decimal(str(final_rate)))

    below = threshold * Decimal(str(final_rate))
    above = (base - threshold) * Decimal(str(progressive["rate_above"]))
    return _money(below + above)


# ── R-CONV ─────────────────────────────────────────────────────────────────

def _apply_convention(answers, refbooks, country, income, nk_rate, v, flag,
                      as_of_date=None) -> float:
    """Возвращает итоговую ставку с учётом конвенции."""
    # R-CONV-02. Офшор — конвенция не применяется.
    if country.is_offshore:
        v.kpn.basis.append("ст. 682 п. 2 — конвенция к офшорным юрисдикциям не применяется")
        return nk_rate

    # R-CONV-07. Уплата за счёт собственных средств.
    if v.decide("own-funds", answers.get("S7.7") == "yes"):
        flag("F-OWN-FUNDS")
        v.kpn.basis.append("ст. 698 п. 3 — налог за счёт собственных средств, "
                           "международный договор не применяется")
        return nk_rate

    # R-CONV-01.
    if not country.has_convention:
        return nk_rate
    document = _residency_document(answers)
    if document != "ok":
        # Документа нет, он под вопросом, его ждут — либо он есть, но
        # пользователь сознательно считает по кодексу. Все четыре случая
        # дают один исход R-CONV-05, и именно здесь важнее всего показать,
        # во что обошлось отсутствие документа.
        v.decide("R-CONV-05", False)
        if document == "declined":
            v.kpn.basis.append("ст. 682 п. 1 — конвенция не применяется "
                               "по решению налогового агента, расчёт по ставкам "
                               "Налогового кодекса")
            return nk_rate
        if document == "doubtful":
            flag("F-CERT-DOUBTFUL")
        v.kpn.basis.append("ст. 705 п. 3 — документ, подтверждающий резидентство, "
                           "не получен либо не отвечает требованиям ст. 702, "
                           "удержание по ставке НК")
        v.kpn.basis.append("ст. 699–701 — нерезидент вправе подать заявление "
                           "на возврат налога из бюджета")

        # Напоминание о сроке ст. 705 п. 3 поднимается, ТОЛЬКО если документ
        # реально спасёт деньги. Иначе флаг встанет на каждой второй операции,
        # и к третьему экрану пользователь перестанет читать флаги вообще —
        # то же самое, что случается с красным цветом, когда его слишком много.
        #
        # При признаках постоянного учреждения флаг гасится совсем: если ПУ
        # образовалось, вся конструкция «удержали у источника и применили
        # конвенцию» под вопросом, и совет собирать сертификат уводит
        # бухгалтера от настоящей проблемы. Один стоп-сигнал вместо двух
        # разнонаправленных подсказок.
        if ("F-PE-RISK" not in v.flags
                and _document_would_lower_the_tax(answers, refbooks, country,
                                                  income, nk_rate)
                and _certificate_deadline_open(answers, as_of_date)):
            flag("F-CERT-DEADLINE")
        return nk_rate

    # R-CONV-05. Документ есть и соответствует ст. 702 — конвенция работает.
    v.decide("R-CONV-05", True)

    return _convention_tail(answers, refbooks, country, income, nk_rate, v, flag)


def _convention_tail(answers, refbooks, country, income, nk_rate, v, flag) -> float:
    """Что даёт конвенция ПОСЛЕ того, как документ признан годным.

    Вынесено отдельно, чтобы этот же путь можно было прогнать вхолостую —
    на выброшенном вердикте и без флагов — и узнать, изменит ли документ
    сумму вообще. Считать это отдельным предикатом нельзя: он разойдётся
    с настоящей веткой, и мы будем обещать пользователю экономию, которой
    в расчёте нет.
    """
    # R-CONV-06. Транзитная структура — вывод не даём.
    if v.decide("conduit", answers.get("S7.6") == "yes"):
        flag("F-CONDUIT")
        v.kpn.basis.append("ст. 698 п. 1 — конвенция не применяется в интересах "
                           "третьего лица")
        return nk_rate

    # ст. 706 п. 1 — доход, связанный с ПУ, освобождению не подлежит.
    if v.decide("pe-linked-income", answers.get("S7.4") == "yes"):
        v.kpn.basis.append("ст. 706 п. 1 — доход связан с постоянным учреждением")
        return nk_rate

    if income in REDUCED_RATE_INCOME:
        # R-CONV-04. Дивиденды, вознаграждения, роялти — пониженная ставка
        # по ст. 10/11/12 конкретной конвенции, а не полное освобождение.
        if not v.decide("R-CONV-04", answers.get("S7.5") == "yes"):
            v.kpn.basis.append("ст. 706 — не подтверждён окончательный получатель дохода")
            return nk_rate

        v.kpn.convention_applied = True
        v.kpn.convention_type = "reduced"
        return _treaty_rate(answers, refbooks, country, income, nk_rate, v, flag)

    # R-CONV-03. Полное освобождение.
    v.kpn.convention_applied = True
    v.kpn.convention_type = "full"
    v.kpn.basis.append("ст. 705 + ст. 7 конвенции — освобождение от налогообложения в РК")
    return 0.0


def _document_would_lower_the_tax(answers, refbooks, country, income,
                                  nk_rate) -> bool:
    """Изменит ли годный документ сумму налога.

    Прогоняем настоящую ветку конвенции на выброшенном вердикте: флаги
    глушим, обоснование уходит в никуда, важен только полученный процент.
    Если он не ниже ставки кодекса — документ ничего не спасает, и говорить
    о сроке его получения незачем.
    """
    if nk_rate is None:
        return False
    try:
        rate = _convention_tail(answers, refbooks, country, income, nk_rate,
                                Verdict(), lambda _code: None)
    except EngineError:
        return False
    return rate is not None and rate < nk_rate


def _certificate_deadline_open(answers, as_of_date) -> bool:
    """Не истёк ли срок ст. 705 п. 3.

    Документ представляется налоговому агенту не позднее 31 марта года,
    следующего за годом выплаты дохода. Срок прошёл — собирать документ
    поздно, и напоминание о нём становится шумом.
    """
    payment = answers.get("S4.2") or answers.get("S4.1")
    if payment is None or as_of_date is None:
        return True                    # дат не знаем — молчать не будем
    return as_of_date <= date(payment.year + 1, 3, 31)


# ── Ставки по конвенциям ───────────────────────────────────────────────────

# Какой блок справочника отвечает за какой вид дохода.
TREATY_BLOCK = {DIVIDENDS: "dividends", ROYALTY: "royalties", INTEREST: "interest"}


def _treaty_rate(answers, refbooks, country, income, nk_rate, v, flag):
    """Предельная ставка по конвенции из справочной таблицы.

    Источник вторичный — сводная таблица консультанта, а не текст конвенции,
    поэтому ставка всегда сопровождается флагом F-TREATY-RATE. Где в таблице
    запись неоднозначна (`confidence: manual_review`), числа не даём вовсе:
    работает уровень обязательства из disclaimer.manual_review_policy.
    """
    record = (refbooks["conventions"].get("rates") or {}).get(country.iso or "")
    if not record:
        # Конвенция есть, но ставки по ней в справочнике нет — ставка НК,
        # выдумывать нечего.
        v.kpn.basis.append(
            f"ст. 706 — в справочнике нет ставок по конвенции с {country.iso}, "
            "применена ставка Налогового кодекса")
        return nk_rate

    if record.get("mli"):
        # MLI добавляет требование владения долей не менее 365 дней и тест
        # основной цели — для пониженной ставки это существенно.
        flag("F-MLI")

    block = record.get(TREATY_BLOCK[income]) or {}

    if block.get("confidence") == CONFIDENCE_MANUAL:
        v.kpn.rate_undetermined = True
        v.kpn.treaty_note = block.get("note") or block.get("raw")
        v.kpn.needs_manual_treaty_rate = True
        v.kpn.basis.append(
            "ст. 706 + ст. 10/11/12 конвенции — ставка в справочной таблице "
            "записана неоднозначно, вывод не даётся")
        flag("F-TREATY-RATE")
        return None

    pct = _treaty_pct(answers, block, income, v)
    if pct is None:
        v.kpn.rate_undetermined = True
        v.kpn.treaty_note = block.get("raw")
        v.kpn.needs_manual_treaty_rate = True
        v.kpn.basis.append("ст. 706 — ставка по конвенции в справочнике не указана")
        flag("F-TREATY-RATE")
        return None

    flag("F-TREATY-RATE")
    treaty_rate = pct / 100

    # Абзац после пп. 9) п. 1 ст. 682: налогоплательщик ВПРАВЕ применить ставки
    # международного договора. Договорная ставка — потолок, а не замена: если
    # ставка кодекса ниже, применяется кодекс. Проверяем по всем видам дохода,
    # а не только по дивидендам.
    if nk_rate is not None and nk_rate < treaty_rate:
        flag("F-TREATY-CEILING")
        v.kpn.basis.append(
            f"ст. 682 п. 1 — ставка кодекса {nk_rate:.0%} ниже договорной "
            f"{pct:g} %, применяется кодекс: договорная ставка это потолок")
        return nk_rate

    v.kpn.basis.append(
        f"ст. 706 + ст. 10/11/12 конвенции с {country.iso} — предельная ставка "
        f"{pct:g} % (справочная таблица, {block.get('raw', '')})".rstrip(", )") + ")")
    return treaty_rate


def _residency_document(answers) -> str:
    """Состояние документа о резидентстве нерезидента (ст. 702).

    Один вопрос вместо двух. Прежде спрашивалось и «хотите применить
    конвенцию», и «получен ли документ» — первое не вопрос желания
    (ст. 682 даёт право, но право обусловлено документом), а второе
    дублировало первое. Отдельная галочка S7.2a оставлена для редкого,
    но существующего случая: документ есть, а считать решили по кодексу.
    """
    answer = answers.get("S7.2")
    if answer == "yes" and answers.get("S7.2a") is True:
        return "declined"
    if answer == "yes":
        # Совместимость со старыми черновиками, где соответствие ст. 702
        # спрашивалось отдельным вопросом S7.3.
        legacy = answers.get("S7.3")
        return "ok" if legacy in (None, "", "yes") else "no"
    if answer in ("doubtful", "pending", "no", None, ""):
        return answer or "no"
    return "no"


def _treaty_pct(answers, block, income, v=None):
    """Процент из блока справочника. Для дивидендов зависит от доли участия.

    R-CONV-08 — порог, установленный САМОЙ КОНВЕНЦИЕЙ. Это не R-KPN-08:
    тот про спор пп. 5) и пп. 6) ст. 682, то есть про норму кодекса. Обе
    развилки висят на одном ответе S5.8, но нормы разные.
    """
    if income != DIVIDENDS:
        return block.get("pct")

    threshold = block.get("ownership_threshold_pct")
    share = (answers.get("S5.8") or {}).get("share_pct")
    reached = (threshold is not None and share is not None
               and share >= threshold)
    if v is not None and threshold is not None:
        v.decide("R-CONV-08", reached)
    return block.get("reduced_pct") if reached else block.get("default_pct")


# ── R-VAT ──────────────────────────────────────────────────────────────────

def _apply_vat(answers, refbooks, country, kind, income, base_kzt, v, flag) -> None:
    vat_rate = refbooks["constants"]["vat_rate"]

    # R-VAT-00. Главный гейт: оборот возникает только у плательщика НДС.
    if not v.decide("vat-payer", answers.get("S1.4") == "yes"):
        flag("F-VAT-THRESHOLD")
        v.vat = VatObligation(
            applicable=False,
            reason="Вы не состоите на регистрационном учёте по НДС: оборот по "
                   "приобретению работ и услуг от нерезидента не возникает.",
            basis="ст. 454 п. 1")
        return

    # Поставка товара без работ и услуг — не оборот по приобретению.
    if income == GOODS and answers.get("S5.3") != "yes":
        v.vat = VatObligation(
            applicable=False,
            reason="Поставка товаров — не оборот по приобретению работ и услуг. "
                   "НДС уплачивается при импорте.",
            basis="ст. 454")
        return

    # R-VAT-08. Исключения ст. 454 п. 3.
    exemption = answers.get("S10")
    if v.decide("vat-exemption-454", bool(exemption)):
        known = {e["id"] for e in refbooks["vat_exemptions_454_3"]}
        if exemption not in known:
            raise EngineError(f"Неизвестное исключение по НДС «{exemption}»")
        v.vat = VatObligation(applicable=False,
                              reason="Применяется исключение по ст. 454 п. 3.",
                              basis="ст. 454 п. 3")
        return

    # Обороты, для которых работ и услуг нет вовсе.
    if income in {DIVIDENDS, PENALTY, CAPITAL_GAIN, INTEREST}:
        v.vat = VatObligation(
            applicable=False,
            reason="Выплата не является оборотом по приобретению работ и услуг.",
            basis="ст. 454 п. 1")
        return

    kind = _kind_for_vat(income, kind, refbooks)
    rule = _vat_place_rule(country, kind, income)
    place_rules = refbooks["vat_place_rules"]
    if kind and kind.get("flag"):
        flag(kind["flag"])

    basis_article = ("ст. 515 и Приложение № 18 к Договору о ЕАЭС"
                     if country.is_eaeu else "ст. 459 п. 2")

    if rule == "manual_review":
        v.vat = VatObligation(
            applicable=None,
            place_of_supply=None,
            reason="Определение места реализации для этого вида услуг требует "
                   "ручной проверки — движок вывод не даёт.",
            basis=f"{basis_article}, правило приоритета п. 5")
        return

    place_is_kz = _place_is_kz(rule, answers)
    # Место реализации — развилка, от которой зависит вся ветка НДС.
    # Неопределённость (None) фиксируем как «не применилось»: вывода нет.
    v.decide("place-of-supply", bool(place_is_kz))
    if place_is_kz is None:
        v.vat = VatObligation(
            applicable=None,
            reason="Не хватает ответа о фактическом месте выполнения работ.",
            basis=f"{basis_article} {place_rules[rule]['subpoint']}")
        return

    if not place_is_kz:
        v.vat = VatObligation(
            applicable=False, place_of_supply="не РК",
            reason="Место реализации работ и услуг — не Республика Казахстан.",
            basis=f"{basis_article} {place_rules[rule]['subpoint']}")
        return

    # R-VAT-01/02. База — стоимость по акту, включая КПН у источника.
    v.vat = VatObligation(
        applicable=True, rate=vat_rate, base_kzt=base_kzt,
        amount_kzt=_money(Decimal(str(base_kzt)) * Decimal(str(vat_rate))),
        place_of_supply="РК",
        reason="Место реализации — Республика Казахстан.",
        basis="ст. 454, 463, 502, 503")


def _kind_for_vat(income, kind, refbooks) -> Optional[dict]:
    """Вид услуги учитывается только там, где он осмыслен.

    S5.5 задаётся в ветках «работы и услуги», «товары с работами в РК» и
    «аренда». Для дивидендов, роялти и международной перевозки вид услуги не
    спрашивается, и подставлять его нельзя — иначе место реализации определится
    по чужому правилу.

    Для международной перевозки берём запись `transport` из справочника: там и
    правило (по исполнителю), и флаг F-TRANSPORT.
    """
    if income in {SERVICES, GOODS, RENT}:
        return kind
    if income == TRANSPORT_INTL:
        return _service_kind("transport", refbooks)
    return None


def _vat_place_rule(country, kind, income) -> str:
    """Правило определения места реализации."""
    if kind:
        return kind["vat_place_rule_eaeu"] if country.is_eaeu else kind["vat_place_rule"]
    if income == ROYALTY:
        return "buyer"                     # права на ИС — ст. 459 п. 2 пп. 4)
    # Остаточное правило ст. 459 п. 2 пп. 5) — по месту нахождения исполнителя.
    return "performer"


def _place_is_kz(rule: str, answers: dict) -> Optional[bool]:
    if rule == "buyer":
        return True                        # покупатель — резидент РК
    if rule == "performer":
        return False                       # исполнитель — нерезидент
    if rule == "real_estate":
        return _kz_answer(answers.get("S9.3"))
    if rule in {"actual_place_movable", "actual_place_event"}:
        # Место фактического выполнения: отдельный ответ S9.3, иначе место
        # оказания услуг из блока S6.
        explicit = _kz_answer(answers.get("S9.3"))
        return explicit if explicit is not None else _kz_answer(answers.get("S6.1"))
    return None


def _kz_answer(value: Optional[str]) -> Optional[bool]:
    if value in (None, ""):
        return None
    return value == IN_KZ


# ── Периоды и сроки ────────────────────────────────────────────────────────

def _apply_periods_and_deadlines(answers, refbooks, payment_date, act_date, v, flag) -> None:
    # Квартал формы определяется датой, на которую доход ПРИЗНАН, а не датой
    # ухода денег. При авансе, закрытом более поздним актом, это дата акта:
    # «предоплата — это ещё не доход нерезидента» (ст. 684 п. 1 пп. 3).
    #
    # Дату признания уже вычислил разрешитель R-DATE — берём её, а не считаем
    # заново. Прежде срок уплаты шёл от правила, а квартал от даты выплаты,
    # и они расходились: срок в октябре при форме за II квартал. Найдено
    # прогоном консультации K05 (аванс 20.04, акт 25.09 → форма за III
    # квартал, уплата до 25.10), где это и было названо прямым текстом.
    rule = v.date_rule
    kpn_date = (rule.fx_date if rule is not None and rule.fx_date
                else payment_date or act_date)
    v.periods = Periods(
        kpn_quarter=_quarter(kpn_date), kpn_year=kpn_date.year if kpn_date else None,
        vat_quarter=_quarter(act_date), vat_year=act_date.year if act_date else None)

    if v.periods.kpn_quarter and v.periods.vat_quarter \
            and v.periods.kpn_quarter != v.periods.vat_quarter:
        flag("F-PERIOD-MISMATCH")

    deadlines = refbooks["deadlines"]
    if kpn_date:
        # Срок ставит правило R-DATE — у него своя норма под каждый случай.
        # Здесь остаётся запасной вариант на случай, когда правило срока
        # не дало: 25 календарных дней после окончания месяца признания.
        if v.deadlines.kpn_payment is None:
            v.deadlines.kpn_payment = _plus_days(_end_of_month(kpn_date),
                                                 KPN_PAYMENT_DAYS_AFTER_MONTH)
        quarter_key = f"q{v.periods.kpn_quarter}"
        form = deadlines["form_101_04"].get(quarter_key, {})
        v.deadlines.form_101_04 = _iso(form.get("date_2026"))
    if v.periods.vat_quarter and v.vat.applicable:
        v.deadlines.vat_payment = _iso(deadlines["vat_payment"].get(
            f"q{v.periods.vat_quarter}"))


# ── R-REP ──────────────────────────────────────────────────────────────────

def _apply_reporting(answers, refbooks, v, flag, usd_rate=None) -> None:
    quarter = v.periods.kpn_quarter
    v.reporting.period = f"{MONTH_ROMAN.get(quarter, quarter)} квартал {v.periods.kpn_year}" \
        if quarter else None

    accrual = answers.get("S5.9") or {}
    # Аванс без начисления дохода — это R-DATE-02: оплата есть, акта нет.
    # Прежде состояние приходило ярлыком S5.9.accrued, теперь выводится
    # из фактов; ярлык принимается только из старых черновиков.
    open_advance = (v.date_rule is not None
                    and v.date_rule.rule_id == "R-DATE-02")
    if open_advance or accrual.get("accrued") is False:
        # R-KPN-19. Аванс без начисления дохода в форму не попадает вовсе.
        v.reporting.reported_in_form = False
        v.reporting.form_101_04_required = False
        v.basis.append("R-KPN-19 — аванс без начисления дохода в 101.04 не отражается")
        return

    if v.kpn.taxable:
        # R-REP-01. Порог к облагаемым доходам не применяется.
        v.reporting.form_101_04_required = True
        v.reporting.reported_in_form = True
        v.reporting.threshold_applied = False
        return

    # R-REP-02/03. Необлагаемые суммы раскрываются только по валютному договору
    # (R-REP-08) и только при превышении порога за отчётный квартал (R-REP-09).
    v.reporting.threshold_applied = True
    flag("F-DISCLOSURE-50K")
    threshold = refbooks["constants"]["disclosure_threshold_usd"]

    # R-REP-08: нет валютного договора — раскрывать нечего независимо от суммы.
    if not v.decide("R-REP-02", bool(answers.get("S2.5"))):
        v.reporting.form_101_04_required = False
        v.reporting.reported_in_form = False
        return

    amount_usd = _amount_in_usd(answers, usd_rate)
    if amount_usd is None:
        # Курса доллара на дату нет — порог не проверен. Молча пропускать нельзя:
        # договор на 60 000 EUR заведомо выше порога, и «раскрывать нечего»
        # обернётся несданной формой.
        v.reporting.threshold_checked = False
        v.reporting.form_101_04_required = False
        v.reporting.reported_in_form = False
        flag("F-THRESHOLD-FX")
        return

    above = amount_usd > threshold
    v.reporting.form_101_04_required = above
    v.reporting.reported_in_form = above


def _amount_in_usd(answers: dict, usd_rate: Optional[float]) -> Optional[float]:
    """Сумма договора в долларах для сравнения с порогом раскрытия.

    Договор в долларах сравнивается напрямую. В любой другой валюте сумма
    сначала приводится к тенге по курсу договора (S4.5), затем делится на
    официальный курс доллара на ту же дату. Нет курса доллара — возвращаем
    None, и вызывающий код помечает порог как непроверенный.
    """
    amount = float(answers.get("S4.4") or 0)
    if answers.get("S1.5") == "USD":
        return amount

    if not usd_rate:
        return None
    amount_kzt = float(Decimal(str(amount)) * Decimal(str(answers.get("S4.5") or 1)))
    return amount_kzt / float(usd_rate)


# ── Маршрут по физлицу ─────────────────────────────────────────────────────

def _individual_route(answers, refbooks, country, v, payment_date) -> Verdict:
    spec = refbooks.get("ipn_nonresident")
    if not spec:
        raise EngineError("В справочнике нет раздела ipn_nonresident")

    v.route = ROUTE_INDIVIDUAL
    contract = answers.get("S2.6") or "gph"
    rate_entry = next((r for r in spec["rates"] if r["code"] == contract), None)
    if rate_entry is None:
        raise EngineError(f"В ipn_nonresident нет ставки для «{contract}»")

    status = "eaeu" if country.is_eaeu else "third_country"

    def applies(contribution: dict) -> bool:
        value = contribution.get(status)
        if isinstance(value, bool):
            return value
        # Текстовые оговорки вида «только по трудовому договору».
        return contract == "employment" and "трудов" in str(value)

    by_code = {c["code"]: c for c in spec["contributions"]}
    v.individual = IndividualRoute(
        ipn_rate=rate_entry["rate"],
        opv=applies(by_code["opv"]),
        vosms=applies(by_code["vosms"]),
        oosms=applies(by_code["oosms"]),
        so=applies(by_code["so"]),
        requires_iin=country.is_eaeu,
        form=spec["form"]["code"],
        appendix=spec["form"]["appendix"],
        basis=[rate_entry["basis"], spec["withholding"]["basis_transfer"]],
    )
    if country.is_eaeu:
        v.basis.append(spec["blockers"][0]["text"])

    if payment_date:
        # ст. 692 п. 6 — 25 число месяца, СЛЕДУЮЩЕГО за месяцем удержания.
        following = _plus_months(date(payment_date.year, payment_date.month, 1), 1)
        v.deadlines.ipn_payment = date(following.year, following.month, IPN_TRANSFER_DAY)

    v.periods = Periods(kpn_quarter=_quarter(payment_date),
                        kpn_year=payment_date.year if payment_date else None)
    v.reporting = Reporting(form_101_04_required=False, reported_in_form=False)
    v.basis.append("R-ROUTE-02 — выплаты физлицам-нерезидентам отражаются "
                   "в форме 200.00, приложение 200.02")
    return v


# ── Графы приложения и строки расчёта ──────────────────────────────────────

def _fill_graphs(answers, refbooks, country, kind, v) -> None:
    counterparty = answers.get("S2.4") or {}
    payment_date = answers.get("S4.2")
    income = answers.get("S5.1")

    graphs: dict[str, Any] = {}
    if payment_date and (v.date_rule is None
                         or v.date_rule.rule_id not in ("R-DATE-06", "R-DATE-07")):
        # R-FORM-03: графа B не заполняется для начисленных, но невыплаченных —
        # а это теперь вывод правила R-DATE, а не отдельный вариант ответа.
        graphs["B"] = f"{payment_date.month:02d}"
    graphs["C"] = counterparty.get("name")
    graphs["D"] = country.graph_d
    graphs["E"] = counterparty.get("tin")
    graphs["F"] = _income_code(answers, country, kind)

    # R-FORM-04: для дивидендов реквизиты контракта не заполняются —
    # основанием служит протокол общего собрания.
    if income != DIVIDENDS:
        graphs["G"] = counterparty.get("contract_no")

    graphs["H"] = v.kpn.base_kzt
    graphs["I"] = round(v.kpn.rate * 100, 2) if v.kpn.rate is not None else None
    graphs["J"] = v.kpn.amount_kzt

    # R-FORM-02: графа Q заполняется и при пониженной ставке, не только при
    # полном освобождении.
    if v.kpn.convention_applied:
        graphs["Q"] = v.kpn.base_kzt
        graphs["R"] = _primary_treaty_code(refbooks)
        graphs["T"] = country.iso

    if v.reporting.threshold_applied and v.reporting.form_101_04_required:
        # Необлагаемые суммы: W — доход, X — сумма, не подлежащая обложению.
        graphs["W"] = v.kpn.base_kzt or _money(
            Decimal(str(answers.get("S4.4") or 0)) * Decimal(str(answers.get("S4.5") or 1)))
        graphs["X"] = graphs["W"]

    graphs["Y"] = answers.get("S2.5")
    v.graphs = graphs

    month = _month_of_quarter(payment_date)
    if v.reporting.reported_in_form and month:
        v.lines = {
            "101.04.001": {MONTH_ROMAN[month]: v.kpn.base_kzt},
            "101.04.002": {MONTH_ROMAN[month]: v.kpn.amount_kzt},
        }


def _primary_treaty_code(refbooks: dict) -> str:
    for entry in refbooks["treaty_codes"]:
        if entry.get("primary"):
            return entry["code"]
    raise EngineError("В справочнике treaty_codes нет основной конвенции")


# ── Уверенность вывода ─────────────────────────────────────────────────────

def _confidence(v: Verdict) -> str:
    if v.vat.applicable is None or v.kpn.rate_undetermined or "F-CONDUIT" in v.flags:
        return CONFIDENCE_MANUAL
    if "F-THRESHOLD-FX" in v.flags:
        return CONFIDENCE_MANUAL
    if v.kpn.needs_manual_treaty_rate:
        return CONFIDENCE_LIKELY
    return CONFIDENCE_CONFIRMED


# ── Сводка по кварталу ─────────────────────────────────────────────────────

def aggregate_form(verdicts: list[Verdict]) -> FormLines:
    """Строки 101.04.001 и 101.04.002 по месяцам квартала и итогом.

    Складываются только операции, попадающие в форму: аванс без начисления
    дохода строки не создаёт (R-KPN-19).
    """
    line_001 = {"I": 0, "II": 0, "III": 0}
    line_002 = {"I": 0, "II": 0, "III": 0}

    for v in verdicts:
        if v.out_of_scope:
            # Операция за периметром в расчёт квартала не входит: у неё нет
            # ни базы, ни налога, и ноль в сумме читался бы как «посчитали».
            continue
        for month, amount in (v.lines.get("101.04.001") or {}).items():
            line_001[month] += amount
        for month, amount in (v.lines.get("101.04.002") or {}).items():
            line_002[month] += amount

    line_001["IV"] = sum(line_001[m] for m in ("I", "II", "III"))
    line_002["IV"] = sum(line_002[m] for m in ("I", "II", "III"))
    return FormLines(line_001=line_001, line_002=line_002)
