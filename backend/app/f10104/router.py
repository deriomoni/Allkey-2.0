"""API помогайки по форме 101.04.

Модуль закрыт сервисом `f10104` (`status: beta`, роль `employee`), поэтому все
эндпоинты идут через `require_service` — это граница безопасности модуля, а не
украшение. Внутренняя бета достигается записью в реестре сервисов; отдельного
feature flag в проекте нет.

**Stateless, как модуль кадров.** Ответы визарда приходят в теле POST, считаются
и уходят обратно. На сервере не остаётся ни черновика, ни истории прохождений:
данные о контрагентах клиента — чужие персональные и коммерческие данные, и
хранить их незачем. Реквизиты контрагента и суммы передаются только в теле
запроса, никогда в path или query, и не логируются.

Курс доллара для проверки порога 50 000 USD добывается здесь, а не в движке:
`evaluate` обязан оставаться чистой функцией без обращений к сети.
"""
from datetime import date
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.f10104.engine import EngineError, Verdict, aggregate_form, evaluate
from app.f10104.explain import explain
from app.rates.nbrk_rates import NbrkRates
from app.f10104.rules import (
    country_options, get_country_names, get_rules, mrp_to_kzt, resolve_article,
)
from app.f10104.schemas import AggregateRequest, EvaluateRequest, FlagInfo
from app.personnel.rates import get_rates
from app.services.dependencies import require_service
from app.users.models import User

SERVICE_CODE = "f10104"

# Даты приходят из JSON строками — движок ждёт объекты date.
DATE_ANSWERS = ("S4.1", "S4.2", "S4.3")

# Даты, лежащие ВНУТРИ ответа-объекта. Их легко забыть: верхний уровень
# разбирается циклом, а вложенная дата тихо доезжает до движка строкой
# и падает уже там. Пара — ключ ответа и ключ внутри него.
NESTED_DATE_ANSWERS = (("S4.2a", "rest_payment_date"),)

# Один клиент на процесс: кэш курсов общий для всех пользователей. Курс за
# прошедшую дату не меняется никогда, поэтому первый запросивший квартал
# оплачивает загрузку за всех. Кэш пока в памяти — постоянный кэш в PostgreSQL
# описан в ZADANIE-kursy-valyut.md и делается отдельно.
_rates_client = NbrkRates()

router = APIRouter(prefix="/f10104", tags=["f10104"])


@router.get("/meta")
async def meta(_: User = Depends(require_service(SERVICE_CODE))) -> dict:
    """Версия справочника, объём загруженных данных и константы года.

    Константы года берутся из `personnel/rates.py`: в справочнике 101.04 их нет,
    чтобы не заводить второй источник истины по МРП и МЗП.
    """
    rules = get_rules()
    year = get_rates()

    return {
        "rules_version": rules["meta"]["rules_version"],
        "valid_from": rules["meta"]["valid_from"],
        "tax_code": rules["meta"]["tax_code"],
        "status": rules["meta"]["status"],
        "refbooks": {
            "kpn_rates": len(rules["kpn_rates"]),
            "service_kinds": len(rules["service_kinds"]),
            "income_codes": len(rules["income_codes"]["list"]),
            "offshore_list": len(rules["offshore_list"]["list"]),
            "conventions": len(rules["conventions"]["countries"]),
            "flags": len(rules["flags"]),
        },
        "constants": {
            "source": "app/personnel/rates.py",
            "mrp": year.mrp,
            "mzp": year.mzp,
            "vat_rate": rules["constants"]["vat_rate"],
            "vat_registration_threshold_mrp": rules["constants"]["vat_registration_threshold_mrp"],
            "vat_registration_threshold_kzt": mrp_to_kzt(
                rules["constants"]["vat_registration_threshold_mrp"]
            ),
        },
        "engine": "ready",
    }


@router.get("/refbooks")
async def refbooks(_: User = Depends(require_service(SERVICE_CODE))) -> dict:
    """Справочники для выпадающих списков визарда.

    Признаки «офшор», «есть конвенция», «ЕАЭС» считаются на сервере: это нормы,
    и интерфейс не должен знать, какая страна к чему относится. Виды услуг
    отдаются с группой A/B — по ней визард показывает подсказку про ст. 679
    п. 1 пп. 3), не зная самой нормы.
    """
    rules = get_rules()
    return {
        "rules_version": rules["meta"]["rules_version"],
        "countries": country_options(),
        "currencies": get_country_names()["currencies"],
        "service_kinds": [
            {"id": kind["id"], "label": kind["label"], "group": kind["group"]}
            for kind in rules["service_kinds"]
        ],
        # Тексты предупреждений целиком: визард показывает их по ходу, как только
        # ответ включает условие, а не только на экране результата. Формулировки
        # живут в справочнике, интерфейс их не сочиняет.
        "flags": {code: _flag_info(code).model_dump() for code in rules["flags"]},
        # Исключения ст. 454 п. 3 — чек-лист на шаге S9. Формулировки из
        # справочника: интерфейс их не сочиняет.
        "vat_exemptions": rules["vat_exemptions_454_3"],
        # Спорная ставка по дивидендам: обе позиции, тексты и правила выбора.
        # Визард показывает их дословно — своей редакции спорной нормы у него
        # быть не может, иначе на экране окажется третья версия текста.
        "disputed_dividends": _disputed_dividends(),
        # Тексты экранов выхода за периметр. Формулировок в TypeScript быть
        # не должно: вариант остаётся в списке, и то, что пользователь увидит
        # вместо расчёта, — такая же налоговая формулировка, как остальные.
        "out_of_scope": {k: v for k, v in
                         (get_rules().get("out_of_scope") or {}).items()
                         if not k.startswith("_")},
        # Подсказки под вопросами анкеты и памятка по документу
        # о резидентстве. Формулировок в TypeScript быть не должно.
        "question_hints": {k: v for k, v in
                           (get_rules().get("question_hints") or {}).items()
                           if not k.startswith("_")},
        "cert_memo": get_rules().get("cert_memo") or {},
        # Дисклеймер и правило manual_review — целиком из справочника.
        # Версия, дата справочника и дата формирования подставляются здесь:
        # в интерфейсе не должно остаться константы, которую забудут поправить.
        "disclaimer": _disclaimer(),
    }


@router.get("/article")
async def article(
    ref: str,
    _: User = Depends(require_service(SERVICE_CODE)),
) -> dict:
    """Текст статьи Налогового кодекса по ссылке вида «ст. 682 п. 1 пп. 5)».

    Ленивая загрузка по клику: файл статей 417 КБ, отдавать его вместе со
    справочниками нельзя. Кэшируется навсегда — текст кодекса в пределах
    редакции не меняется.

    Ссылки на конвенции сюда не ведут: «ст. 10 конвенции» и «ст. 10 НК» —
    разные нормы, и резолвер их различает.
    """
    return resolve_article(ref)


@router.post("/evaluate")
async def evaluate_operation(
    payload: EvaluateRequest,
    _: User = Depends(require_service(SERVICE_CODE)),
) -> dict:
    """Расчёт обязательств по одной операции. Ничего не сохраняет."""
    answers = _prepare(payload.answers)
    usd_rate = await _usd_rate_if_needed(answers)
    verdict = _run(answers, payload.as_of_date, usd_rate)
    result = _serialize(verdict)
    # Блок 2 экрана результата (ТЗ §6). Собирается здесь, а не на фронте:
    # формулировки живут в справочнике, и переносить их в TypeScript значило бы
    # завести вторую редакцию налоговых текстов.
    result["explanation"] = asdict(
        explain(answers, get_rules(), verdict,
                payload.as_of_date or date.today(), usd_rate))
    return result


@router.post("/aggregate")
async def aggregate_quarter(
    payload: AggregateRequest,
    _: User = Depends(require_service(SERVICE_CODE)),
) -> dict:
    """Строки основного расчёта 101.04.001 и 101.04.002 за квартал.

    Принимает список операций, возвращает и сами вердикты, и сводку по строкам —
    чтобы экран результата не пересчитывал операции повторно.
    """
    verdicts = []
    for raw in payload.operations:
        answers = _prepare(raw)
        usd_rate = await _usd_rate_if_needed(answers)
        verdicts.append(_run(answers, payload.as_of_date, usd_rate))

    lines = aggregate_form(verdicts)
    return {
        "rules_version": get_rules()["meta"]["rules_version"],
        "lines": {"101.04.001": lines.line_001, "101.04.002": lines.line_002},
        "operations": [_serialize(v) for v in verdicts],
    }


# ── Внутреннее ─────────────────────────────────────────────────────────────

def _prepare(answers: dict[str, Any]) -> dict[str, Any]:
    """Копия ответов с датами, разобранными из ISO-строк.

    Работаем с копией: движок входные данные не меняет, и здесь тоже не должны.
    """
    prepared = dict(answers)
    for key in DATE_ANSWERS:
        prepared[key] = _as_date(prepared.get(key), key)

    for key, inner in NESTED_DATE_ANSWERS:
        block = prepared.get(key)
        if isinstance(block, dict) and block.get(inner) is not None:
            block = dict(block)                      # не трогаем вход
            block[inner] = _as_date(block[inner], f"{key}.{inner}")
            prepared[key] = block

    return prepared


def _as_date(value: Any, key: str):
    """ISO-строка в дату. Не строка — возвращаем как есть."""
    if not isinstance(value, str) or not value:
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ответ {key}: ожидается дата в формате ГГГГ-ММ-ДД") from e


def _run(answers: dict, as_of: Optional[date], usd_rate: Optional[float]) -> Verdict:
    on = as_of or answers.get("S4.2") or answers.get("S4.1") or date.today()
    try:
        return evaluate(answers, refbooks=get_rules(), as_of_date=on, usd_rate=usd_rate)
    except EngineError as e:
        # Не хватает ответа либо справочник не знает значения — это ошибка ввода,
        # а не сбой сервера.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


async def _usd_rate_if_needed(answers: dict) -> Optional[float]:
    """Официальный курс доллара на дату выплаты — только когда он реально нужен.

    Нужен для сравнения необлагаемой суммы с порогом 50 000 USD, если договор
    заключён не в долларах. Раскрытие вообще применяется только к выплатам в
    рамках валютного договора (R-REP-08), поэтому без УНК курс не запрашиваем.

    Сбой НБ РК не роняет расчёт: возвращаем None, движок пометит порог
    непроверенным и поставит manual_review.
    """
    if answers.get("S1.5") == "USD" or not answers.get("S2.5"):
        return None

    day = answers.get("S4.2") or answers.get("S4.1")
    if not isinstance(day, date):
        return None

    try:
        official = await _rates_client.get_official_rate("USD", day)
    except Exception:                      # noqa: BLE001 — сеть, таймаут, разбор
        return None
    return official.rate if official else None


def _serialize(verdict: Verdict) -> dict:
    """Вердикт в JSON плюс тексты сработавших флагов из справочника."""
    payload = asdict(verdict)
    payload.pop("_flag_severity", None)
    payload.pop("decisions", None)   # журнал развилок отдаётся разобранным
                                     # в explanation, сырой он фронту не нужен
    payload["flags_detail"] = [
        _flag_info(code).model_dump() for code in verdict.flags
    ]
    return payload


def _disputed_dividends() -> dict:
    """Позиции по спорной ставке дивидендов и условия выбора (R-KPN-08)."""
    record = next(r for r in get_rules()["kpn_rates"]
                  if r["code"] == "dividends_25")
    return {
        "label": record.get("label"),
        "positions": record.get("positions") or [],
        "what_to_check": record.get("what_to_check"),
        "money_at_stake": record.get("money_at_stake"),
        "user_resolution": record.get("user_resolution") or {},
    }


def _disclaimer() -> dict:
    """Тексты дисклеймера с подставленными версией и датами."""
    rules = get_rules()
    block = rules["disclaimer"]
    values = {
        "rules_version": rules["meta"]["rules_version"],
        "rules_date": rules["meta"]["generated"],
        "generated_at": date.today().isoformat(),
    }
    return {
        "text": block["text"].format(**values),
        "print_footer": block["print_footer"].format(**values),
        "manual_review_banner": block["manual_review_banner"],
        # Отдельный текст для экрана выхода. Переписывать общий под два разных
        # экрана значило бы ослабить его для обоих: на выходе нет расчёта,
        # а общий начинается со слов «помогайка формирует расчёт».
        "out_of_scope_text": (block.get("out_of_scope_text") or "").format(**values),
    }


def _flag_info(code: str) -> FlagInfo:
    spec = get_rules()["flags"].get(code, {})
    return FlagInfo(
        code=code,
        severity=spec.get("severity", "info"),
        title=spec.get("title", code),
        text=spec.get("text", ""),
        basis=spec.get("basis"),
    )
