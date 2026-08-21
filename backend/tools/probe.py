"""Прогон произвольных ситуаций через живую помогайку — три колонки.

Для сверки с консультациями uchet.kz и «Параграфа»: кейс задаётся коротко,
результат печатается так, чтобы его можно было положить рядом с текстом
ответа специалиста и сравнить глазом.

    python tools/probe.py cases/consultations.py
    python tools/probe.py cases/consultations.py --only PU-1,ROY-2
    python tools/probe.py cases/consultations.py --local

По умолчанию ходит на ПРОД тем же путём, что и страница: POST /f10104/evaluate
с тем же телом. `--local` переключает на 127.0.0.1:8000.

Файл кейсов — обычный Python со списком CASES. Каждый кейс это кортеж
(идентификатор, что за ситуация, ответы, ожидания). Ожидания необязательны:
если их нет, колонка «ждали» пуста, и это нормально — при разборе консультации
ожидаемое часто становится понятно только после прогона.

    CASES = [
        ("PU-1", "Стройплощадка 8 месяцев, консультация uchet.kz от 03.2026",
         case(S2_3="TR", S5_1="services", S3_4="construction", amount=50000),
         {"kpn.rate": 0.20, "flag:F-PE-RISK": True}),
    ]

Помощник `case()` заполняет обязательные поля значениями по умолчанию,
чтобы кейс занимал строку, а не экран. Ключи пишутся через подчёркивание
(`S2_3`), точки расставляются сами.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROD = "https://api.allkey.kz"
LOCAL = "http://127.0.0.1:8000"

# Минимальный набор ответов, без которого движок не считает. Всё, что кейс
# не переопределяет, берётся отсюда: обычная выплата резиденту Германии
# за консультационные услуги, плательщик НДС, без конвенции.
DEFAULTS = {
    "S1.1": {"quarter": 1, "year": 2026},
    "S1.2": "small", "S1.3": "yes", "S1.4": "yes", "S1.5": "KZT",
    "S2.1": "money", "S2.2": "legal_entity", "S2.3": "DE",
    "S2.4": {"name": "Nonresident", "tin": "X1", "contract_no": "1",
             "contract_date": "2026-01-10"},
    "S3.1": "no", "S3.4": "none",
    "S4.1": "2026-02-20", "S4.2": "2026-03-10", "S4.4": 10000.0, "S4.5": 1.0,
    "S5.1": "services", "S5.5": "consulting", "S6.1": "outside",
    "S7.2": "no",
}


def case(**over) -> dict:
    """Ответы кейса. Ключи через подчёркивание: S2_3 → S2.3, amount → S4.4."""
    answers = json.loads(json.dumps(DEFAULTS))       # глубокая копия
    aliases = {"amount": "S4.4", "rate": "S4.5", "country": "S2.3",
               "income": "S5.1", "act": "S4.1", "paid": "S4.2",
               "currency": "S1.5"}
    for key, value in over.items():
        key = aliases.get(key, key.replace("_", ".", 1) if key.startswith("S") else key)
        if value is None:
            answers.pop(key, None)
        else:
            answers[key] = value
    return answers


# ── Обращение к сервису ────────────────────────────────────────────────────

def token_for(base: str) -> str:
    """Токен из F10104_TOKEN либо логин по F10104_USER / F10104_PASSWORD."""
    ready = os.environ.get("F10104_TOKEN")
    if ready:
        return ready.strip()

    user = os.environ.get("F10104_USER")
    password = os.environ.get("F10104_PASSWORD")
    if not (user and password):
        sys.exit("Нужен F10104_TOKEN либо пара F10104_USER и F10104_PASSWORD "
                 "в переменных окружения. Пароль в командной строке не пишем.")

    body = urllib.parse.urlencode({"username": user, "password": password})
    request = urllib.request.Request(
        f"{base}/auth/login", data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def evaluate(base: str, token: str, answers: dict) -> tuple[dict | None, str | None]:
    payload = json.dumps({"answers": answers}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/f10104/evaluate", data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response), None
    except urllib.error.HTTPError as error:
        return None, f"HTTP {error.code}: {error.read().decode('utf-8')[:180]}"
    except Exception as error:                       # noqa: BLE001
        return None, str(error)


# ── Чтение вердикта ────────────────────────────────────────────────────────

def dig(obj, path: str):
    if path.startswith("flag:"):
        return path[5:] in (obj.get("flags") or [])
    for part in path.split("."):
        obj = (obj or {}).get(part) if isinstance(obj, dict) else None
    return obj


def money(value) -> str:
    return "—" if value is None else f"{int(value):,}".replace(",", " ")


def digest(verdict: dict) -> list[tuple[str, str]]:
    """Короткая выжимка: то, что сравнивают с текстом консультации."""
    kpn, vat = verdict.get("kpn") or {}, verdict.get("vat") or {}
    rule = verdict.get("date_rule") or {}
    periods, deadlines = verdict.get("periods") or {}, verdict.get("deadlines") or {}
    rate = kpn.get("rate")

    rows = [
        ("маршрут", verdict.get("route") or "—"),
        ("уровень", verdict.get("confidence") or "—"),
        ("база КПН", money(kpn.get("base_kzt"))),
        ("ставка", "спорна" if rate is None and kpn.get("taxable")
                   else f"{round(rate * 100, 2):g} %" if rate is not None else "—"),
        ("КПН", money(kpn.get("amount_kzt"))),
        ("НДС", "не возникает" if vat.get("applicable") is False
                else "требует решения" if vat.get("applicable") is None
                else money(vat.get("amount_kzt"))),
        ("код дохода", str((verdict.get("graphs") or {}).get("F") or "—")),
        ("норма даты", f"{rule.get('rule_id') or '—'} {rule.get('subparagraph') or ''}".strip()),
        ("курс на", str(rule.get("fx_date") or "—")),
        ("срок КПН", str(deadlines.get("kpn_payment") or "—")),
        ("период", f"{periods.get('kpn_quarter') or '—'} кв. {periods.get('kpn_year') or ''}".strip()),
        ("флаги", ", ".join(verdict.get("flags") or []) or "—"),
    ]
    if kpn.get("position_chosen"):
        rows.append(("позиция", str(kpn["position_chosen"])))
    return rows


def compare(verdict: dict, expected: dict | None) -> list[str]:
    if not expected:
        return []
    diffs = []
    for path, want in expected.items():
        got = dig(verdict, path)
        if got != want:
            diffs.append(f"{path}: ждали {want!r}, получили {got!r}")
    return diffs


# ── Печать ─────────────────────────────────────────────────────────────────

def report(case_id: str, title: str, verdict: dict, expected, error) -> bool:
    print()
    print("═" * 78)
    print(f"{case_id} · {title}")
    print("═" * 78)
    if error:
        print(f"  ОШИБКА: {error}")
        return False

    rows = digest(verdict)
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"  {name:<{width}}   {value}")

    rule = verdict.get("date_rule") or {}
    if rule.get("explanation"):
        print()
        print("  норма словами:")
        for line in _wrap(rule["explanation"], 72):
            print(f"    {line}")

    diffs = compare(verdict, expected)
    if expected:
        print()
        if diffs:
            print("  РАСХОЖДЕНИЯ С ОЖИДАНИЕМ:")
            for d in diffs:
                print(f"    · {d}")
        else:
            print("  сошлось с ожиданием")
    return not diffs


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


# ── Точка входа ────────────────────────────────────────────────────────────

def load_cases(path: str) -> list:
    spec = importlib.util.spec_from_file_location("probe_cases", path)
    module = importlib.util.module_from_spec(spec)
    module.case = case                               # помощник доступен файлу
    spec.loader.exec_module(module)
    return module.CASES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", help="файл со списком CASES")
    parser.add_argument("--local", action="store_true", help="бить в 127.0.0.1:8000")
    parser.add_argument("--only", help="через запятую: прогнать только эти кейсы")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    base = LOCAL if args.local else PROD
    cases = load_cases(args.cases)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c[0] in wanted]

    token = token_for(base)
    print(f"Прогон {len(cases)} ситуаций через {base}")

    matched, failed, no_expectation = 0, [], 0
    for entry in cases:
        case_id, title, answers = entry[0], entry[1], entry[2]
        expected = entry[3] if len(entry) > 3 else None
        verdict, error = evaluate(base, token, answers)
        ok = report(case_id, title, verdict, expected, error)
        if error or (expected and not ok):
            failed.append(case_id)
        elif expected:
            matched += 1
        else:
            no_expectation += 1

    print()
    print("═" * 78)
    print(f"ИТОГ: {len(cases)} ситуаций · сошлось {matched} · "
          f"без ожиданий {no_expectation} · разошлось {len(failed)}")
    if failed:
        print("  разошлись: " + ", ".join(failed))
        print()
        print("  Разбирать в этом порядке, не считая заранее, что права помогайка:")
        print("    1) ошиблась помогайка;")
        print("    2) консультация опирается на прежний кодекс (ст. 644–648);")
        print("    3) случай за периметром первой версии.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
