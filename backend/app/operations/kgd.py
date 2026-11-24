"""Клиент API КГД «Сведения по контрагентам (Открытые данные)».

Описание — инструкция с портала КГД (kgd.gov.kz → «Сведения по контрагентам» → «Ссылка на API»):
    POST {host}/services/isnaportal/public/get-sur-data
    заголовок X-Portal-Token: <токен>, тело {"xin": "<БИН/ИИН>"}
Хост в инструкции не указан; рабочий — https://kgd.gov.kz (проверено 23.11.2026).
В инструкции поля — объекты {ru, kk}; фактический ответ — плоские строки. Нормализатор
принимает оба вида.

Токен — только из окружения (KGD_API_TOKEN в backend/.env), в коде, логах, ответах и
сообщениях об ошибках его нет. На боевой сервер не переносится (там переменной нет —
модуль отвечает 409 «токен не настроен»).

В лог — только код ответа и тип ошибки, без БИН (раздел 1.1 ТЗ, п. 6).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from app.operations.config import get_ops_settings

logger = logging.getLogger("app.operations")

XIN_RE = re.compile(r"^\d{12}$")
NO_DATA = "нет данных"

# Признаки риска из ответа: ключ API → подпись. Любое значение, кроме «Нет данных», — риск.
RISK_FIELDS = {
    "inactive": "бездействующий",
    "registrationInvalid": "регистрация признана недействительной",
    "reRegistrationInvalid": "перерегистрация признана недействительной",
    "operationsWOWork": "сделки без фактического выполнения работ",
    "esfRestrinctions": "ограничение выписки ЭСФ",
    "regAddressAbsent": "отсутствует по месту нахождения",
    "bankrupt": "банкрот",
    "selfRegulatoryRegistry": "реестр СРО",
    "courtDecisionRegistry": "реестр по решениям суда",
}
DEBT_FIELDS = ("taxDebt", "taxDebt1", "taxDebt2", "taxDebt3", "taxDebt4")


class KgdError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _ru(v: Any) -> Any:
    """{ru, kk} → ru; строка/число/None — как есть."""
    if isinstance(v, dict):
        return v.get("ru")
    return v


def _has_value(v: Any) -> bool:
    s = str(_ru(v) or "").strip()
    return bool(s) and s.lower() != NO_DATA


def regime_code(tax_mode: Optional[str]) -> Optional[str]:
    """Режим из текста КГД → значение tax.regime карточки (general | simplified | retail | agricultural) или None."""
    s = (tax_mode or "").lower()
    if not s or s == NO_DATA:
        return None
    if "общеустановлен" in s:
        return "general"
    if "упрощен" in s or "упрощён" in s:
        return "simplified"
    if "розничн" in s:
        return "retail"
    if "крестьян" in s or "фермер" in s:
        return "agricultural"   # СНР для КФХ (владелец, 24.11.2026)
    return None


def vat_payer(vat_info: Optional[str], vat_date: Optional[str]) -> Optional[bool]:
    """НДС из ответа КГД. «Нет данных» без даты — не плательщик (сверено с профилями кабинета 23.11.2026)."""
    s = (vat_info or "").strip().lower()
    if vat_date:
        return not ("снят" in s)
    if not s or s == NO_DATA:
        return False
    if "снят" in s or "не является" in s:
        return False
    if s == "да" or "плательщик" in s or "состоит" in s or "постановк" in s:
        return True
    return None  # незнакомая формулировка — решает человек


def normalize(raw: dict) -> dict:
    """Ответ КГД → поля для карточки. Только то, что API действительно отдаёт."""
    tax_mode = _ru(raw.get("taxMode"))
    vat_info = _ru(raw.get("vatInfo"))
    risks = {k: _ru(raw.get(k)) for k in RISK_FIELDS if _has_value(raw.get(k))}
    debts = {k: float(raw.get(k) or 0) for k in DEBT_FIELDS if raw.get(k) is not None}
    stats = [s for s in (raw.get("statistics") or []) if isinstance(s, dict) and s.get("year")]
    return {
        "xin": raw.get("xin"),
        "actuality": raw.get("actuality"),
        "name": _ru(raw.get("name")),
        "reg_date": raw.get("regDate"),
        "residency": _ru(raw.get("residency")),
        "oked": _ru(raw.get("oked")),
        "oked_name": _ru(raw.get("okedName")),
        "oked_date": raw.get("okedDate"),
        "tax_mode": tax_mode,
        # taxModeDate — дата постановки в текущем ОГД (указание владельца 23.11.2026),
        # НЕ дата перехода на режим: как дату режима не использовать.
        "ogd_reg_date": raw.get("taxModeDate"),
        "regime": regime_code(tax_mode),
        "vat_info": vat_info,
        "vat_date": raw.get("vatDate"),
        "vat_payer": vat_payer(vat_info, raw.get("vatDate")),
        "risks": {k: {"label": RISK_FIELDS[k], "value": v} for k, v in risks.items()},
        "tax_debt": debts,
        # Отрицательная задолженность — переплата, не сигнал.
        "has_debt": any(v > 0 for v in debts.values()),
        "overpayment": any(v < 0 for v in debts.values()),
        "headcount": {int(s["year"]): s.get("workersCount") for s in stats},
        "knn": {int(s["year"]): {"knn": s.get("knn"), "knn_avg": s.get("knnAvg")} for s in stats},
        # Явного статуса («действующий / ликвидация») API не отдаёт — выводим из признаков риска.
        "status": "бездействующий" if "inactive" in risks else ("есть признаки риска" if risks else "нет признаков риска"),
    }


def fetch_raw(xin: str, timeout: float = 30.0) -> dict:
    xin = (xin or "").strip()
    if not XIN_RE.match(xin):
        raise KgdError("БИН/ИИН — 12 цифр", 400)
    s = get_ops_settings()
    token = s.kgd_api_token.get_secret_value() if s.kgd_api_token else ""
    if not token:
        raise KgdError("Токен КГД не настроен (KGD_API_TOKEN)", 409)
    req = urllib.request.Request(
        s.kgd_api_url,
        data=json.dumps({"xin": xin}).encode(),
        headers={"X-Portal-Token": token, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        logger.warning("kgd: HTTP %s", e.code)
        msg = {400: "КГД: ошибка в запросе", 401: "КГД: токен не принят", 403: "КГД: токен не принят",
               404: "КГД: доступ к сервису запрещён или БИН не найден", 500: "КГД: ошибка на сервере"}
        raise KgdError(msg.get(e.code, f"КГД: ответ {e.code}"), 502 if e.code >= 500 else 424)
    except Exception as e:  # noqa: BLE001
        logger.warning("kgd: %s", type(e).__name__)
        raise KgdError("КГД недоступен", 502)
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise KgdError("КГД: ответ не JSON", 502)
    if not isinstance(data, dict) or not data.get("xin"):
        raise KgdError("КГД: по этому БИН/ИИН данных нет", 404)
    return data


def check(xin: str) -> dict:
    raw = fetch_raw(xin)
    return {"normalized": normalize(raw), "raw": raw}


class MaskBinInAccessLog(logging.Filter):
    """uvicorn.access: маскирует bin=… в строке запроса /api/ops/kgd (БИН не должен попадать в логи)."""

    _re = re.compile(r"(bin|xin)=\d+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._re.sub(r"\1=***", a) if isinstance(a, str) else a for a in record.args)
        return True


def install_log_mask() -> None:
    lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, MaskBinInAccessLog) for f in lg.filters):
        lg.addFilter(MaskBinInAccessLog())
