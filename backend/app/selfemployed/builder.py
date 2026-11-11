"""
Сборка контекста docxtpl для договора с самозанятым. Модуль stateless:
данные формы -> контекст -> docx в памяти, ничего не сохраняется (как кадровый
модуль: ИИН/ФИО не пишутся в БД, не попадают в логи и в URL).

Числа прописью, склонение ФИО и должности, проверки ИИН/БИН — общие хелперы
кадрового модуля (`app.personnel.helpers`), своих копий здесь нет.
"""
from __future__ import annotations

import math
import re
from datetime import date
from io import BytesIO
from pathlib import Path

from docxtpl import DocxTemplate, RichText

from app.personnel.helpers.fio import GENITIVE, fio_full, inflect_phrase
from app.personnel.helpers.iin import is_valid_bin, is_valid_iin
from app.personnel.helpers.numbers import format_figures, pluralize_ru, ru_int_to_words
from app.selfemployed.profiles import PROFILES, ROLES

TEMPLATE = Path(__file__).parent / "templates" / "dogovor_samozanyatyi.docx"

# МРП на 1 января года (п. 2 ст. 718 НК РК: предел — 300 МРП в месяц).
# На новый год добавить значение — иначе check() предупредит, а в п. 5.1
# вместо суммы останется «300 МРП».
MRP = {2026: 4325}
LIMIT_MRP_PER_MONTH = 300

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]

PAYMENT_METHODS = {
    "cashless": "безналичным способом на банковский счет {E_gen}, указанный в разделе 9",
    "any": "наличным или безналичным способом",
}
RENT_PERIODS = {"month": "в месяц", "term": "за весь срок аренды"}
DEFAULT_PAYMENT_DAYS = 20


# --------------------------------------------------------------------------- утилиты
def int_words(n: int) -> str:
    """Число прописью по-русски — общий хелпер кадрового модуля."""
    return ru_int_to_words(n)


def fmt_amount(n: int) -> str:
    """300000 -> '300 000' (общий хелпер кадрового модуля)."""
    return format_figures(n)


def days_phrase(n: int, kind: str) -> str:
    """20 (двадцать) рабочих дней / 1 (один) рабочий день / 30 (тридцать) календарных дней."""
    adj = {"work": ("рабочий", "рабочих", "рабочих"),
           "cal": ("календарный", "календарных", "календарных")}[kind]
    return (f"{n} ({int_words(n)}) {pluralize_ru(n, adj)} "
            f"{pluralize_ru(n, ('день', 'дня', 'дней'))}")


def date_quoted(d: date) -> str:
    return f"«{d.day:02d}» {MONTHS_GEN[d.month - 1]} {d.year} г."


def date_long(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year} года"


def short_name(full: str) -> str:
    """Иванов Иван Иванович -> Иванов И.И."""
    parts = full.split()
    if not parts:
        return ""
    return parts[0] + (" " + "".join(p[0] + "." for p in parts[1:3]) if len(parts) > 1 else "")


def gender_from_iin(iin: str) -> str | None:
    """7-я цифра ИИН: 1,3,5 — мужской; 2,4,6 — женский. Пол в форме не спрашиваем."""
    if not re.fullmatch(r"\d{12}", (iin or "").strip()):
        return None
    d = iin[6]
    return "m" if d in "135" else "f" if d in "246" else None


def gender_from_name(full: str) -> str:
    """Пол руководителя по отчеству (рус./каз.)."""
    s = (full or "").lower()
    if re.search(r"(вна|кызы|қызы)\b", s):
        return "f"
    return "m"


def head_genitive(full: str) -> str:
    """«Сейткалиева Айгерим Маратовна» -> «Сейткалиевой Айгерим Маратовны».

    Склонение — общий хелпер на pymorphy3 из кадрового модуля; пол берётся из
    отчества. Значение остаётся редактируемым в форме (head_name_gen), поэтому
    редкий случай бухгалтер поправит руками."""
    parts = (full or "").split()
    if not parts:
        return ""
    gender = "female" if gender_from_name(full) == "f" else "male"
    last, first, middle = (parts + ["", ""])[:3]
    return fio_full(last, first, middle, case=GENITIVE, gender=gender)


def position_genitive(position: str) -> str:
    """«Директор» -> «директора» (родительный падеж, со строчной — как в преамбуле)."""
    declined = inflect_phrase(position or "", GENITIVE)
    return declined[:1].lower() + declined[1:] if declined else ""


def months_between(start: date, end: date) -> int:
    return max(1, (end.year - start.year) * 12 + end.month - start.month + (1 if end.day >= start.day else 0))


def monthly_limit(year: int) -> int | None:
    m = MRP.get(year)
    return m * LIMIT_MRP_PER_MONTH if m else None


# --------------------------------------------------------------------------- роли и тексты
def role_map(profile: dict) -> dict:
    c, e = ("lessee", "lessor") if profile["kind"] == "rent" else ("customer", "executor")
    out = {}
    for prefix, key in (("C", c), ("E", e)):
        forms = ROLES[key]
        out[prefix] = forms["nom"]
        for case in ("gen", "dat", "ins"):
            out[f"{prefix}_{case}"] = forms[case]
    return out


def fill(text: str, vars_: dict) -> str:
    return text.format_map(vars_)


def numbered(sec_no: int, items: list, vars_: dict) -> list:
    return [
        {"num": f"{sec_no}.{i}.", "text": fill(it["text"], vars_),
         "bullets": [fill(b, vars_) for b in it.get("bullets", [])]}
        for i, it in enumerate(items, 1)
    ]


# --------------------------------------------------------------------------- проверки
def check(data: dict) -> list[str]:
    """Предупреждения для формы (не блокируют генерацию)."""
    w = []
    p = PROFILES[data["oked"]]
    contract_date: date = data["contract_date"]
    start: date = data.get("valid_from") or contract_date
    end: date = data["valid_to"]
    if end < start:
        w.append("Дата окончания договора раньше даты начала.")
    limit = monthly_limit(contract_date.year)
    if limit is None:
        w.append(f"Не задан МРП на {contract_date.year} год — предел дохода в п. 5.1 не рассчитан.")
    else:
        months = months_between(start, end)
        amount = data["amount"]
        per_month = amount if (p["kind"] == "rent" and data.get("rent_period", "month") == "month") \
            else math.ceil(amount / months)
        if per_month > limit:
            w.append(f"Сумма в месяц ≈ {fmt_amount(per_month)} тг превышает предел самозанятого "
                     f"{fmt_amount(limit)} тг (300 МРП).")
    if not is_valid_iin(data["executor"]["iin"]):
        w.append("ИИН исполнителя не прошел проверку: неверная контрольная сумма "
                 "или несуществующая дата рождения.")
    customer_id = (data["customer"].get("bin") or "").strip()
    if customer_id and not is_valid_bin(customer_id):
        label = "ИИН" if data["customer"].get("org_form") == "ИП" else "БИН"
        w.append(f"{label} заказчика не прошел проверку: неверная контрольная сумма.")
    if "___" in data.get("subject", ""):
        w.append("В предмете договора остались незаполненные места «___».")
    return w


# --------------------------------------------------------------------------- контекст
def build_context(data: dict) -> dict:
    p = PROFILES[data["oked"]]
    rv = role_map(p)
    rent = p["kind"] == "rent"
    subject = (data.get("subject") or p["default_subject"]).strip()
    vars_ = {**rv, "subject": subject}

    cust, ex = data["customer"], data["executor"]
    contract_date: date = data["contract_date"]
    amount = int(data["amount"])
    pay_days = int(data.get("payment_days") or DEFAULT_PAYMENT_DAYS)
    limit = monthly_limit(contract_date.year)

    # ---- преамбула: Заказчик
    head = cust.get("head_name", "").strip()
    head_gen = (cust.get("head_name_gen") or "").strip() or head_genitive(head)
    acting = "действующей" if gender_from_name(head) == "f" else "действующего"
    form = cust.get("org_form", "ТОО")
    position_gen = ((cust.get("position_gen") or "").strip()
                    or position_genitive(cust.get("position") or "Директор") or "директора")
    rt = RichText()
    if form == "ИП":
        rt.add(f"ИП «{cust['name']}»", bold=True)
        rt.add(f", ИИН {cust['bin']}, в лице {head_gen}, {acting} на основании уведомления о начале "
               f"деятельности в качестве индивидуального предпринимателя, именуемый в дальнейшем ")
    else:
        rt.add(f"{form} «{cust['name']}»", bold=True)
        rt.add(f", БИН {cust['bin']}, в лице {position_gen} {head_gen}, {acting} "
               f"на основании {cust.get('basis_gen', 'Устава')}, именуемое в дальнейшем ")
    rt.add(f"«{rv['C']}»", bold=True)
    rt.add(", с одной стороны, и ")

    # ---- преамбула: Исполнитель
    g = gender_from_iin(ex["iin"]) or "m"
    status = ex.get("status", "citizen")
    who = ("кандас" if status == "kandas"
           else "гражданка Республики Казахстан" if g == "f" else "гражданин Республики Казахстан")
    reg = "зарегистрированная" if g == "f" else "зарегистрированный"
    reg_short = "зарегистрирована" if g == "f" else "зарегистрирован"
    named = "именуемая" if g == "f" else "именуемый"
    rt.add(f"{who} ")
    rt.add(ex["full_name"], bold=True)
    rt.add(f", ИИН {ex['iin']}, {reg} в качестве плательщика специального налогового режима для "
           f"самозанятых, {named} в дальнейшем ")
    rt.add(f"«{rv['E']}»", bold=True)
    rt.add(", с другой стороны, совместно именуемые «Стороны», заключили настоящий договор о нижеследующем:")

    # ---- разделы 1–8
    s = p["sections"]
    sections = []

    def add(title, items):
        no = len(sections) + 1
        sections.append({"num": no, "title": fill(title, vars_), "points": numbered(no, items, vars_)})

    add("ПРЕДМЕТ ДОГОВОРА", s["subject"])

    add("СТАТУС " + rv["E_gen"].upper(), [
        {"text": f"{{E}} подтверждает, что {reg_short} как самозанятое лицо и применяет специальный "
                 f"налоговый режим для самозанятых по виду деятельности {p['code']} «{p['name']}», включенному "
                 f"в Перечень, утвержденный постановлением Правительства Республики Казахстан "
                 f"от 21 ноября 2025 года № 994."},
        {"text": "{E} самостоятельно:", "bullets": [
            "исчисляет и уплачивает налоги и социальные платежи;",
            "несет ответственность за соблюдение условий специального налогового режима, в том числе "
            "предельного размера дохода;",
            "ведет учет доходов при необходимости.",
        ]},
        {"text": "{C} не является налоговым агентом {E_gen}, если иное прямо не предусмотрено законодательством."},
        {"text": "При прекращении применения специального налогового режима для самозанятых {E} письменно "
                 "уведомляет {C_gen} в течение 3 (трех) рабочих дней."},
    ])

    add(s["relations"]["title"], s["relations"]["items"])
    add(s["procedure"]["title"], s["procedure"]["items"])

    method = fill(PAYMENT_METHODS[data.get("payment_method", "cashless")], vars_)
    amount_txt = f"{fmt_amount(amount)} ({int_words(amount)}) тенге"
    limit_txt = (f"{fmt_amount(limit)} ({int_words(limit)}) тенге" if limit else "300 МРП")
    if rent:
        period = RENT_PERIODS[data.get("rent_period", "month")]
        pay_items = [
            {"text": f"Арендная плата составляет {amount_txt} {period}.", "bullets": [
                f"Размер арендной платы по настоящему договору не может превышать 300 МРП в месяц, "
                f"что в {contract_date.year} году составляет {limit_txt}."]},
            {"text": f"Арендная плата вносится {method}. Срок оплаты — {days_phrase(pay_days, 'work')} "
                     + ("с начала оплачиваемого месяца." if data.get("rent_period", "month") == "month"
                        else "с даты подписания акта приема-передачи.")},
            {"text": "Арендная плата включает все налоговые обязательства {E_gen}."},
        ]
        pay_title = "АРЕНДНАЯ ПЛАТА И ПОРЯДОК РАСЧЕТОВ"
    else:
        noun = "работ" if p["kind"] == "works" else "услуг"
        act = "акта выполненных работ" if p["kind"] == "works" else "акта оказанных услуг"
        pay_items = [
            {"text": f"Стоимость {noun} определяется по каждой заявке отдельно. Общая сумма договора "
                     f"составляет {amount_txt}.", "bullets": [
                f"Вознаграждение {{E_gen}} по настоящему договору не может превышать 300 МРП в месяц, "
                f"что в {contract_date.year} году составляет {limit_txt}."]},
            {"text": f"Оплата производится {method}. Срок оплаты — {days_phrase(pay_days, 'work')} "
                     f"с даты подписания {act}."},
            {"text": f"{{E}} подтверждает, что стоимость {noun} включает все его расходы и налоговые обязательства."},
        ]
        pay_title = "СТОИМОСТЬ И ОПЛАТА"
    add(pay_title, pay_items)

    add("ОТВЕТСТВЕННОСТЬ", s["liability"])

    valid_from: date | None = data.get("valid_from")
    start_txt = ("с даты подписания" if not valid_from or valid_from == contract_date
                 else f"с {date_long(valid_from)}")
    add("СРОК ДЕЙСТВИЯ", [
        {"text": f"Договор вступает в силу {start_txt} и действует до {date_long(data['valid_to'])}."},
        {"text": "Срок действия договора может быть продлен по соглашению Сторон."},
        {"text": "Окончание срока действия договора не освобождает Стороны от исполнения обязательств, "
                 "возникших до его окончания."},
    ])

    notice = int(data.get("notice_days") or p["notice_days"])
    settle = ("{C} вносит арендную плату за фактический период пользования и возвращает "
              + ("Помещение" if p["code"] == "68201" else "Имущество") + " по акту возврата."
              if rent else
              "{C} оплачивает фактически выполненные и принятые " +
              ("работы." if p["kind"] == "works" else "услуги."))
    add("РАСТОРЖЕНИЕ И ПРОЧИЕ УСЛОВИЯ", [
        {"text": f"Любая Сторона вправе отказаться от исполнения договора, письменно уведомив другую Сторону. "
                 f"Срок уведомления — не менее {days_phrase(notice, 'cal')} до даты расторжения."},
        {"text": "При расторжении договора " + settle},
        {"text": "Споры разрешаются путем переговоров, а при недостижении согласия — в суде в соответствии "
                 "с законодательством Республики Казахстан."},
        {"text": "Договор составлен в двух экземплярах, имеющих одинаковую юридическую силу, "
                 "по одному для каждой Стороны."},
    ])

    # ---- реквизиты
    def lines(pairs):
        return [f"{k}: {v}" for k, v in pairs if v]

    cust_title = f"ИП «{cust['name']}»" if form == "ИП" else f"{form} «{cust['name']}»"
    cust_lines = lines([
        ("ИИН" if form == "ИП" else "БИН", cust.get("bin")),
        ("Адрес", cust.get("address")), ("ИИК", cust.get("iik")), ("Банк", cust.get("bank")),
        ("БИК", cust.get("bik")), ("Тел.", cust.get("phone")), ("E-mail", cust.get("email")),
    ])
    ex_lines = lines([
        ("ИИН", ex.get("iin")), ("Адрес", ex.get("address")), ("ИИК", ex.get("iik")),
        ("Банк", ex.get("bank")), ("БИК", ex.get("bik")), ("Тел.", ex.get("phone")),
    ])

    return {
        "title": p["title"],
        "number": data.get("number") or "____",
        "city": data.get("city") or "г. Алматы",
        "date": date_quoted(contract_date),
        "preamble": rt,
        "sections": sections,
        "req_no": len(sections) + 1,
        "role_c": rv["C"], "role_e": rv["E"],
        "cust_title": cust_title, "cust_lines": cust_lines,
        "cust_pos": cust.get("position", "Директор") if form != "ИП" else "Индивидуальный предприниматель",
        "cust_sign": f"____________ / {short_name(head)} /",
        "ex_title": ex["full_name"], "ex_lines": ex_lines,
        "ex_pos": "",
        "ex_sign": f"____________ / {short_name(ex['full_name'])} /",
    }


def render(data: dict) -> bytes:
    tpl = DocxTemplate(str(TEMPLATE))
    tpl.render(build_context(data))
    buf = BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def filename(data: dict) -> str:
    surname = data["executor"]["full_name"].split()[0]
    num = re.sub(r"[^\w-]", "_", str(data.get("number") or "б-н"))
    return f"Договор_{num}_{data['oked']}_{surname}.docx"
