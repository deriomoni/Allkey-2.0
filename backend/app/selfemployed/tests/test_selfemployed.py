"""Договор с самозанятым: рендер по всем 12 ОКЭД и проверки формы.

Правило проекта: шаблон проверяем реальным рендером, не осмотром текста —
поэтому каждый тест читает текст сгенерированного .docx.
"""
from datetime import date
from io import BytesIO

from docx import Document

from app.selfemployed.builder import (
    check, days_phrase, gender_from_iin, head_genitive, position_genitive,
    render, short_name,
)
from app.selfemployed.profiles import ORDER, PROFILES

# ИИН/БИН с верной контрольной суммой: проверки берутся из хелперов personnel.
BASE = dict(
    oked="43310", number="1", contract_date=date(2026, 10, 6), valid_to=date(2026, 12, 31),
    amount=900000,
    customer=dict(org_form="ТОО", name="Тест", bin="210940012346",
                  head_name="Иванов Иван Иванович", head_name_gen="Иванова Ивана Ивановича"),
    executor=dict(full_name="Ахметова Дана Ериковна", iin="950101400121"),
)


def text(data):
    doc = Document(BytesIO(render(data)))
    out = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                out += [p.text for p in cell.paragraphs]
    return "\n".join(out)


def test_all_profiles_render_without_leftover_tags():
    for code in ORDER:
        t = text(dict(BASE, oked=code))
        assert "{" not in t and "}" not in t, code
        assert PROFILES[code]["title"] in t


def test_payment_days_default_and_custom():
    assert "20 (двадцать) рабочих дней" in text(BASE)
    assert "1 (один) рабочий день" in text(dict(BASE, payment_days=1))
    assert "3 (три) рабочих дня" in text(dict(BASE, payment_days=3))


def test_female_executor_and_ip_customer():
    d = dict(BASE, customer=dict(BASE["customer"], org_form="ИП"))
    t = text(d)
    assert "гражданка Республики Казахстан" in t and "именуемая" in t and "ИП «Тест»" in t


def test_limit_warning():
    w = check(dict(BASE, amount=5_000_000, valid_to=date(2026, 11, 30)))
    assert any("превышает предел" in x for x in w)
    assert check(BASE) == []


def test_invalid_iin_and_bin_warn():
    """Проверки ИИН/БИН — хелперы personnel: неверная контрольная сумма ловится."""
    w = check(dict(BASE, executor=dict(BASE["executor"], iin="950101400123")))
    assert any("ИИН исполнителя" in x for x in w)
    w = check(dict(BASE, customer=dict(BASE["customer"], bin="210940012345")))
    assert any("БИН заказчика" in x for x in w)


def test_declension_from_personnel_helpers():
    """ФИО и должность руководителя склоняются сами, если форма не передала падеж."""
    customer = {k: v for k, v in BASE["customer"].items() if k != "head_name_gen"}
    customer["head_name"] = "Сейткалиева Айгерим Маратовна"
    t = text(dict(BASE, customer=customer))
    assert "в лице директора Сейткалиевой Айгерим Маратовны, действующей" in t
    assert head_genitive("Нурланов Ерлан Бакытович") == "Нурланова Ерлана Бакытовича"
    assert position_genitive("Директор") == "директора"


def test_helpers():
    assert gender_from_iin("900515300127") == "m" and gender_from_iin("123") is None
    assert short_name("Нурланов Ерлан Бакытович") == "Нурланов Е.Б."
    assert days_phrase(21, "work") == "21 (двадцать один) рабочий день"
