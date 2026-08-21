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
    # Сумма в валюте договора, облагаемая по пп. 3) СЕЙЧАС. Выводится, а не
    # спрашивается: отдельный вопрос «начислена ли часть суммы» был бы тем же
    # ярлыком состояния, от которых мы ушли. None — правило сумму не сужает.
    taxable_now_fx: Optional[Decimal] = None
    # Часть аванса, которую акт ещё не закрыл: дохода она не образует,
    # но требует возврата к операции.
    advance_unclosed_fx: Optional[Decimal] = None


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

    Ни одного нового вопроса: всё выводится из суммы аванса (S4.2a) и суммы
    по акту (S4.4).

        начислено          = сумма по акту
        по пп. 3) сейчас   = меньшая из двух: аванс и начисленное
        остаток аванса     = аванс сверх начисленного — дохода пока не образует
        остаток акта       = начисленное сверх аванса — идёт по пп. 1)

    Контрольный пример официального разбора: аванс 4 500, акт на 4 000 →
    по пп. 3) облагается 4 000, а 500 остаются незакрытыми.
    """
    advance_amount = partial.get("advance_amount")
    rest_payment = partial.get("rest_payment_date")
    act_amount = answers.get("S4.4")          # начислено = сумма по акту

    advance = Decimal(str(advance_amount)) if advance_amount is not None else None
    accrued = Decimal(str(act_amount)) if act_amount is not None else None

    taxable_now = min(advance, accrued) if advance is not None and accrued is not None else advance
    unclosed = (advance - accrued if advance is not None and accrued is not None
                and advance > accrued else None)
    act_rest = (accrued - advance if advance is not None and accrued is not None
                and accrued > advance else None)

    advance_due = deadline_after_month(act)
    rest_due = deadline_after_month(rest_payment) if rest_payment else None

    parts = [DatePart("начисленная часть", "пп. 3)", taxable_now, act, advance_due)]
    if act_rest is not None:
        parts.append(DatePart("остаток по акту", "пп. 1)", act_rest, rest_payment,
                              rest_due, rest_payment is not None))

    # Возврат за незакрытым остатком аванса — своя причина и свой срок.
    # Смешивать его ни со сроком уплаты, ни с двенадцатимесячной датой
    # по ст. 679 п. 1 пп. 5) нельзя: это три разных обязательства.
    if unclosed is not None:
        control_date = end_of_month(act)
        control_reason = ("Вернуться, когда акт закроет остаток аванса "
                          f"{_num(unclosed)} — дохода он пока не образует")
    elif act_rest is not None and rest_payment is None:
        control_date = end_of_month(act)
        control_reason = "Вернуться после выплаты остатка по акту"
    else:
        control_date = None
        control_reason = None

    return DateVerdict(
        rule_id="R-DATE-04", subparagraph="пп. 3) + пп. 1)",
        fx_date=act, deadline=advance_due, obligation_arisen=True,
        control_date=control_date, control_reason=control_reason,
        norms=["ст. 684 п. 1 пп. 3)", "ст. 684 п. 1 пп. 1)"],
        explanation=_partial_text(act, payment, rest_payment, advance, accrued,
                                  taxable_now, unclosed, act_rest,
                                  advance_due, rest_due),
        parts=parts, taxable_now_fx=taxable_now, advance_unclosed_fx=unclosed,
    )


def _num(value: Optional[Decimal]) -> str:
    if value is None:
        return "—"
    return f"{value:f}".rstrip("0").rstrip(".")


def _partial_text(act, payment, rest_payment, advance, accrued, taxable_now,
                  unclosed, act_rest, advance_due, rest_due) -> str:
    """Объяснение словами. Три разных случая, и путать их нельзя."""
    head = (f"Аванс {_num(advance)} перечислен {_fmt(payment)}, "
            f"акт подписан {_fmt(act)} на {_num(accrued)}. ")

    if unclosed is not None:
        return head + (
            f"Начислено меньше, чем выплачено, поэтому по подпункту 3) пункта 1 "
            f"статьи 684 облагается начисленная часть — {_num(taxable_now)}, "
            f"курс на дату начисления {_fmt(act)}, срок до {_fmt(advance_due)}. "
            f"Остаток аванса {_num(unclosed)} дохода пока не образует: "
            f"вернитесь к операции, когда акт его закроет.")

    if act_rest is not None:
        tail = (f"Остаток по акту {_num(act_rest)} идёт по подпункту 1): курс "
                f"на дату выплаты остатка {_fmt(rest_payment)}, "
                f"срок до {_fmt(rest_due)}."
                if rest_payment else
                f"Остаток по акту {_num(act_rest)} ещё не выплачен — "
                f"по нему обязанность наступит в момент выплаты.")
        return head + (
            f"Это одна операция, но норм две. В пределах предоплаты действует "
            f"подпункт 3) пункта 1 статьи 684: облагается {_num(taxable_now)}, "
            f"курс на дату начисления {_fmt(act)}, срок до {_fmt(advance_due)}. "
        ) + tail

    return head + (
        f"Аванс и начисленное совпали, поэтому вся сумма идёт по подпункту 3) "
        f"пункта 1 статьи 684: курс на дату начисления {_fmt(act)}, "
        f"срок до {_fmt(advance_due)}.")


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
