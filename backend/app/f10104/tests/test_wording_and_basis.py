"""Формулировки и основания, исправленные по замечаниям владельца 20.08.2026.

Тексты помогайки уходят в документ, который подошьют, поэтому неверная ссылка
на норму дороже опечатки. Здесь сторожа именно на те утверждения, которые
оказались неверными, — чтобы они не вернулись при следующей правке текстов.
"""
from app.f10104.rules import get_rules


def flags() -> dict:
    return get_rules()["flags"]


def test_vat_threshold_claims_no_penalty():
    """«15 % от неотражённого оборота плюс 50 МРП» — такой нормы в Налоговом
    кодексе нет. Ст. 101 п. 6 отсылает к ответственности по законам РК, то есть
    в КоАП. Приписывать административную санкцию НК нельзя, а её действующий
    размер мы не проверяли."""
    text = flags()["F-VAT-THRESHOLD"]["text"]

    assert "50 МРП" not in text
    assert "Санкция" not in text
    assert "15 %" not in text


def test_vat_threshold_cites_both_norms_separately():
    """Порог и срок подачи заявления — разные статьи, и ссылка обязана
    различать их: порог 10 000 МРП по ст. 99 п. 4 пп. 2), пять рабочих дней
    по ст. 101 п. 3."""
    flag = flags()["F-VAT-THRESHOLD"]

    assert "ст. 99 п. 4 пп. 2)" in flag["basis"]
    assert "ст. 101 п. 3" in flag["basis"]
    assert "10 000 МРП" in flag["text"]
    assert "пяти рабочих дней" in flag["text"]


def test_no_flag_text_makes_unverified_historical_claims():
    """Утверждения про прежнюю редакцию кодекса проверить нечем: его текста
    у нас нет. По правилу проекта непроверенное не утверждается."""
    suspicious = ("До 2026 года", "ранее обязанность", "раньше обязанность",
                  "в прежней редакции обязанность")
    offenders = [
        f"{code}: {phrase}"
        for code, flag in flags().items()
        for phrase in suspicious
        if phrase in str(flag.get("text", ""))
    ]

    assert not offenders, offenders


def test_every_flag_carries_a_basis():
    """Предупреждение без нормы — мнение, а не вывод."""
    without = [code for code, flag in flags().items() if not flag.get("basis")]

    assert not without, without


# ── Документ о резидентстве: один вопрос вместо двух ───────────────────────

def _run(**over):
    from datetime import date  # noqa: PLC0415

    from app.f10104.engine import evaluate  # noqa: PLC0415

    from .answers import base  # noqa: PLC0415

    # S7.3 гасим намеренно: новый визард его не шлёт, а фикстура ставит
    # значение по умолчанию, и обратная совместимость приняла бы его
    # за ответ старого черновика.
    answers = base(**{"S2.3": "PL", "S5.1": "services", "S5.5": "design",
                      "S6.1": "outside", "S1.5": "EUR", "S4.4": 5000.0,
                      "S4.5": 500.0, "S7.3": None, **over})
    return evaluate(answers, refbooks=get_rules(), as_of_date=date(2026, 9, 30))


def test_convention_applies_only_with_a_conforming_document():
    """Применение конвенции — не вопрос желания. Ст. 682 даёт право, но право
    обусловлено документом, и развилка проходит по нему (ст. 702)."""
    ok = _run(**{"S7.2": "yes", "S7.4": "no", "S7.6": "no"})

    assert ok.kpn.convention_applied is True
    assert ok.kpn.rate == 0.0


def test_missing_or_pending_document_falls_back_to_the_tax_code():
    for answer in ("no", "pending"):
        v = _run(**{"S7.2": answer})

        assert v.kpn.convention_applied is not True, answer
        assert v.kpn.rate == 0.20, answer
        # Налог не потерян — это должно быть сказано, а не подразумеваться.
        assert any("699" in b for b in v.kpn.basis), answer


def test_doubtful_document_is_said_out_loud_not_silently_ignored():
    """«Есть, но требования ст. 702 под вопросом» — не то же самое, что «нет».
    Расчёт идёт по кодексу, но пользователь обязан увидеть, почему."""
    v = _run(**{"S7.2": "doubtful"})

    assert v.kpn.rate == 0.20
    assert "F-CERT-DOUBTFUL" in v.flags
    assert flags()["F-CERT-DOUBTFUL"]["basis"].startswith("ст. 702")


def test_document_present_but_convention_declined_is_a_valid_choice():
    """Редкий, но существующий случай: документ есть, а считают по кодексу."""
    v = _run(**{"S7.2": "yes", "S7.2a": True, "S7.4": "no", "S7.6": "no"})

    assert v.kpn.convention_applied is not True
    assert v.kpn.rate == 0.20
    assert any("по решению налогового агента" in b for b in v.kpn.basis)
    # Здесь про возврат из бюджета говорить незачем: налог удержан по выбору
    # агента при действующем документе, а не из-за его отсутствия.
    assert not any("699" in b for b in v.kpn.basis)


def test_old_drafts_still_read_correctly():
    """Черновики со старым S7.3 не должны молча начать применять конвенцию."""
    old_no = _run(**{"S7.2": "yes", "S7.3": "no"})
    old_yes = _run(**{"S7.2": "yes", "S7.3": "yes", "S7.4": "no", "S7.6": "no"})

    assert old_no.kpn.rate == 0.20
    assert old_yes.kpn.convention_applied is True
