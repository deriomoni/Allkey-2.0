"""Какая норма ст. 684 п. 1 применилась, на какую дату курс и когда платить.

Группа правил R-DATE из ТЗ §4, блок S4-А. Принцип, ради которого модуль
существует, важнее самих правил:

    Бухгалтер не выбирает подпункт статьи 684 и не отвечает на вопрос
    «начислено или выплачено». Он сообщает факты, которые знает без раздумий:
    когда подписан акт, когда ушли деньги, отнесена ли сумма на вычеты,
    рассчитались ли встречной поставкой. Норму выводит движок и объясняет
    словами.

Термины «начислено» и «выплачено» — источник самой частой ошибки начинающего
бухгалтера. Помогайка существует затем, чтобы снять этот выбор, а не
переложить его на пользователя в других словах. Поэтому вопроса
«это аванс или обычная выплата?» здесь нет и быть не должно: стадия
выводится из двух дат.

Модуль чистый: только даты и факты на входе, решение и текст на выходе.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

# ст. 684 п. 1 пп. 1) — 25 календарных дней после окончания месяца.
DAYS_AFTER_MONTH = 25
# ст. 684 п. 1 пп. 2) — 10 календарных дней после срока сдачи декларации по КПН.
DAYS_AFTER_DECLARATION = 10
# Срок сдачи декларации по КПН (форма 100.00) — 31 марта года, следующего
# за отчётным. Дата в справочнике; здесь запасное значение на случай,
# если ключа нет.
DECLARATION_DAY = (3, 31)


@dataclass
class DatePart:
    """Часть операции со своей нормой, своим курсом и своим сроком.

    Обычная операция состоит из одной части. Частичный аванс (R-DATE-04) —
    из двух: аванс идёт по пп. 3), остаток по пп. 1), и это разные даты
    и разные сроки в пределах одной операции.
    """
    label: str
    subparagraph: str
    amount_fx: Optional[Decimal] = None
    fx_date: Optional[date] = None
    deadline: Optional[date] = None
    fx_date_known: bool = True


@dataclass
class DateVerdict:
    """Что решил движок про норму, дату курса и срок."""
    rule_id: str
    subparagraph: Optional[str]
    fx_date: Optional[date] = None
    deadline: Optional[date] = None
    # Обязанность перечислить налог наступила. False — не «ошибка», а
    # законное состояние: аванс без начисления или расход без выплаты.
    obligation_arisen: bool = True
    # Дата, к которой надо вернуться, когда обязанность наступит.
    control_date: Optional[date] = None
    control_reason: Optional[str] = None
    explanation: str = ""
    parts: list[DatePart] = field(default_factory=list)
    norms: list[str] = field(default_factory=list)


# ── Вспомогательное ────────────────────────────────────────────────────────

def end_of_month(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def plus_days(day: date, days: int) -> date:
    return day + timedelta(days=days)


def deadline_after_month(day: Optional[date]) -> Optional[date]:
    """25 календарных дней после окончания месяца — ст. 684 п. 1 пп. 1) и 3)."""
    return plus_days(end_of_month(day), DAYS_AFTER_MONTH) if day else None


def deadline_after_declaration(year: int) -> date:
    """10 календарных дней после срока сдачи декларации по КПН за год.

    Декларация за год сдаётся 31 марта следующего года, поэтому отсчёт идёт
    от 31 марта года, следующего за годом отнесения на вычеты.
    """
    month, day = DECLARATION_DAY
    return plus_days(date(year + 1, month, day), DAYS_AFTER_DECLARATION)


def _fmt(day: Optional[date]) -> str:
    return day.strftime("%d.%m.%Y") if day else "—"


# ── Разрешитель ────────────────────────────────────────────────────────────

def resolve(answers: dict) -> DateVerdict:
    """Выбрать правило R-DATE по фактам и объяснить его словами.

    Порядок проверок не произволен: встречная поставка (пп. 4)) перебивает
    обычный порядок, поэтому идёт первой; долговые бумаги (пп. 1) вместо
    пп. 2)) — исключение из ветки вычетов и стоит внутри неё.
    """
    act = answers.get("S4.1")
    payment = answers.get("S4.2")
    accrual = answers.get("S4.3a") or act          # дата начисления дохода
    counter_supply = _is_counter_supply(answers)
    partial = answers.get("S4.2a") or {}

    # ── R-DATE-05. Встречная поставка резидента — пп. 4)
    if counter_supply:
        return DateVerdict(
            rule_id="R-DATE-05", subparagraph="пп. 4)",
            fx_date=accrual, deadline=deadline_after_month(accrual),
            obligation_arisen=accrual is not None,
            norms=["ст. 684 п. 1 пп. 4)"],
            explanation=(
                f"Расчёт произведён встречной поставкой товаров, работ или услуг "
                f"резидента, поэтому применяется подпункт 4) пункта 1 статьи 684: "
                f"курс берётся на дату начисления дохода — {_fmt(accrual)}, "
                f"а налог перечисляется до {_fmt(deadline_after_month(accrual))} "
                f"в пределах суммы встречных обязательств."
                if accrual else
                "Расчёт произведён встречной поставкой резидента — применяется "
                "подпункт 4) пункта 1 статьи 684. Курс берётся на дату начисления "
                "дохода, а её в ответах пока нет."),
            parts=[DatePart("вся сумма", "пп. 4)", None, accrual,
                            deadline_after_month(accrual), accrual is not None)],
        )

    # ── Оплаты не было
    if payment is None:
        if act is None:
            return DateVerdict(
                rule_id="R-DATE-00", subparagraph=None, obligation_arisen=False,
                explanation="Ни акта, ни оплаты — определять пока нечего.")
        return _no_payment(answers, act)

    # ── Оплата есть, акта нет либо оплата раньше акта — это аванс
    if act is None or payment < act:
        if act is not None and partial.get("mode") == "partial":
            return _partial_advance(answers, act, payment, partial)
        if act is None:
            return _advance_open(payment)
        return _advance_closed(act, payment)

    # ── R-DATE-01. Обычный порядок: акт есть, оплата не раньше акта
    return DateVerdict(
        rule_id="R-DATE-01", subparagraph="пп. 1)",
        fx_date=payment, deadline=deadline_after_month(payment),
        norms=["ст. 684 п. 1 пп. 1)"],
        explanation=(
            f"Акт подписан {_fmt(act)}, деньги перечислены {_fmt(payment)}. "
            f"Доход и начислен, и выплачен, поэтому применяется подпункт 1) "
            f"пункта 1 статьи 684: курс берётся на дату выплаты — {_fmt(payment)}, "
            f"налог перечисляется до {_fmt(deadline_after_month(payment))}."),
        parts=[DatePart("вся сумма", "пп. 1)", None, payment,
                        deadline_after_month(payment))],
    )


def _is_counter_supply(answers: dict) -> bool:
    """Встречная поставка спрашивается один раз.

    В ТЗ она есть и как вариант способа расчёта (S2.1), и отдельным вопросом
    S4.7. Спрашивать об одном и том же дважды нельзя — берём ответ оттуда,
    где он есть, отдавая приоритет способу расчёта.
    """
    if answers.get("S2.1") == "counter_supply":
        return True
    return answers.get("S4.7") == "yes"


def _no_payment(answers: dict, act: date) -> DateVerdict:
    """Акт есть, оплаты нет: пп. 2) при отнесении на вычеты, иначе ждём."""
    deduction = answers.get("S4.6") or {}
    if deduction.get("deducted") is not True:
        # ── R-DATE-07. Обязанность не наступила
        return DateVerdict(
            rule_id="R-DATE-07", subparagraph=None, obligation_arisen=False,
            control_date=end_of_month(act),
            control_reason=("Вернуться к операции, когда сумма будет выплачена "
                            "либо отнесена на вычеты"),
            norms=["ст. 684 п. 1 пп. 2)"],
            explanation=(
                f"Акт подписан {_fmt(act)}, оплаты не было, на вычеты сумма "
                f"не отнесена. Обязанность перечислить налог пока не наступила: "
                f"она возникнет либо при выплате, либо при отнесении на вычеты. "
                f"Контрольная дата поставлена в чек-лист."))

    year = int(deduction.get("year") or act.year)

    # ── R-DATE-08. Вознаграждения по долговым бумагам и депозитам
    if answers.get("S5.10a") == "yes" or deduction.get("long_debt") is True:
        return DateVerdict(
            rule_id="R-DATE-08", subparagraph="пп. 1)",
            fx_date=None, obligation_arisen=False,
            control_reason="Срок пойдёт от месяца фактической выплаты",
            norms=["ст. 684 п. 1 пп. 1)", "ст. 684 п. 1 пп. 2)"],
            explanation=(
                "Вознаграждение по долговым ценным бумагам или депозиту со сроком "
                "погашения позже десяти календарных дней после срока сдачи "
                "декларации по КПН: вместо подпункта 2) применяется подпункт 1), "
                "то есть курс и срок считаются от даты фактической выплаты, "
                "а не от последнего дня налогового периода."),
            parts=[DatePart("вся сумма", "пп. 1)", None, None, None, False)])

    # ── R-DATE-06. Отнесено на вычеты без выплаты
    period_end = date(year, 12, 31)
    due = deadline_after_declaration(year)
    return DateVerdict(
        rule_id="R-DATE-06", subparagraph="пп. 2)",
        fx_date=period_end, deadline=due,
        norms=["ст. 684 п. 1 пп. 2)", "ст. 358 п. 1"],
        explanation=(
            f"Акт подписан {_fmt(act)}, оплаты не было, но сумма отнесена "
            f"на вычеты в декларации за {year} год. Применяется подпункт 2) "
            f"пункта 1 статьи 684: курс берётся на последний день налогового "
            f"периода — {_fmt(period_end)}, а налог перечисляется "
            f"до {_fmt(due)}, то есть в течение десяти календарных дней "
            f"после срока сдачи декларации."),
        parts=[DatePart("вся сумма", "пп. 2)", None, period_end, due)])


def _advance_open(payment: date) -> DateVerdict:
    """R-DATE-02. Аванс есть, акта ещё нет — дата начисления неизвестна."""
    return DateVerdict(
        rule_id="R-DATE-02", subparagraph="пп. 3)",
        fx_date=None, obligation_arisen=False, control_date=end_of_month(payment),
        control_reason="Вернуться к операции после подписания акта",
        norms=["ст. 684 п. 1 пп. 3)"],
        explanation=(
            f"Аванс перечислен {_fmt(payment)}, акт ещё не подписан. Применяется "
            f"подпункт 3) пункта 1 статьи 684: курс возьмётся на дату начисления "
            f"дохода, а не на дату аванса, и срок пойдёт от месяца начисления. "
            f"Пока акта нет, обязанность перечислить налог не наступила — "
            f"контрольная дата поставлена в чек-лист."),
        parts=[DatePart("вся сумма", "пп. 3)", None, None, None, False)])


def _advance_closed(act: date, payment: date) -> DateVerdict:
    """R-DATE-03. Аванс закрыт актом — дата начисления известна."""
    due = deadline_after_month(act)
    return DateVerdict(
        rule_id="R-DATE-03", subparagraph="пп. 3)",
        fx_date=act, deadline=due,
        norms=["ст. 684 п. 1 пп. 3)"],
        explanation=(
            f"Аванс перечислен {_fmt(payment)}, акт подписан позже — {_fmt(act)}. "
            f"Применяется подпункт 3) пункта 1 статьи 684: курс берётся на дату "
            f"начисления дохода — {_fmt(act)}, а не на дату аванса, "
            f"и налог перечисляется до {_fmt(due)}."),
        parts=[DatePart("вся сумма", "пп. 3)", None, act, due)])


def _partial_advance(answers: dict, act: date, payment: date,
                     partial: dict) -> DateVerdict:
    """R-DATE-04. Частичный аванс: одна операция, две нормы, два срока.

    В пределах предоплаты действует подпункт 3) — курс на дату начисления.
    Остаток, выплаченный после акта, идёт по подпункту 1) — курс на дату
    выплаты остатка. Сроки считаются отдельно и могут попасть в разные месяцы.
    """
    advance_amount = partial.get("advance_amount")
    rest_payment = partial.get("rest_payment_date")
    total = answers.get("S4.4")

    advance = Decimal(str(advance_amount)) if advance_amount is not None else None
    rest = (Decimal(str(total)) - advance
            if total is not None and advance is not None else None)

    advance_due = deadline_after_month(act)
    rest_due = deadline_after_month(rest_payment) if rest_payment else None

    parts = [
        DatePart("аванс", "пп. 3)", advance, act, advance_due),
        DatePart("остаток", "пп. 1)", rest, rest_payment, rest_due,
                 rest_payment is not None),
    ]
    return DateVerdict(
        rule_id="R-DATE-04", subparagraph="пп. 3) + пп. 1)",
        fx_date=act, deadline=advance_due,
        obligation_arisen=True,
        control_date=None if rest_payment else end_of_month(act),
        control_reason=None if rest_payment else "Вернуться после выплаты остатка",
        norms=["ст. 684 п. 1 пп. 3)", "ст. 684 п. 1 пп. 1)"],
        explanation=(
            f"Часть суммы перечислена авансом {_fmt(payment)}, акт подписан "
            f"{_fmt(act)}, остаток выплачен {_fmt(rest_payment)}. Это одна "
            f"операция, но норм две. В пределах предоплаты действует подпункт 3) "
            f"пункта 1 статьи 684: курс на дату начисления — {_fmt(act)}, "
            f"срок до {_fmt(advance_due)}. Остаток идёт по подпункту 1): курс "
            f"на дату выплаты остатка — {_fmt(rest_payment)}, "
            f"срок до {_fmt(rest_due)}."
            if rest_payment else
            f"Часть суммы перечислена авансом {_fmt(payment)}, акт подписан "
            f"{_fmt(act)}, остаток ещё не выплачен. В пределах предоплаты "
            f"действует подпункт 3) пункта 1 статьи 684: курс на дату "
            f"начисления — {_fmt(act)}, срок до {_fmt(advance_due)}. По остатку "
            f"обязанность наступит в момент выплаты — контрольная дата "
            f"в чек-листе."),
        parts=parts,
    )


# Подсказка «более поздняя дата» — проверка себя, а НЕ правило. В кодексе
# такого правила нет, есть отдельное правило под каждый случай, и подавать
# это как норму нельзя.
LATER_DATE_HINT = (
    "В двух самых частых случаях применяется более поздняя из двух дат: "
    "при обычной оплате — дата выплаты, при авансе — дата начисления. "
    "Исключение — доход, отнесённый на вычеты без выплаты: там дата "
    "не связана ни с актом, ни с оплатой. Это способ проверить себя, "
    "а не норма: в кодексе под каждый случай своё правило."
)
