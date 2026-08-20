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
