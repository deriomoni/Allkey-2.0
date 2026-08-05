"""End-to-end test of the docx engine against the real prikaz_o_prieme template.

Sample entities are plain namespaces (context builders are duck-typed and never
touch the DB), so this runs without sqlalchemy — only docxtpl + pymorphy3 +
num2words.
"""
import re
import zipfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.personnel.context import build_order_context, build_deductions_context
from app.personnel.generator import render_template, output_filename


def sample_entities():
    company = SimpleNamespace(
        name_ru="ТОО «Ромашка»", name_kk="", bin="150640001237", city="Алматы",
        legal_address="г. Алматы, ул. Абая, 1", actual_address="",
        director_fio_ru="Иванов Иван Иванович", director_gender="male",
        signatory_position="Директор", acts_on_basis="Устава",
    )
    employee = SimpleNamespace(
        last_name="Климов", first_name="Василий", middle_name="Александрович",
        iin="900715312346", gender="male",
        document_type="id_card", document_number="012345678",
        document_issued_by="МВД РК", document_issue_date=date(2015, 3, 15),
        actual_address="г. Алматы, ул. Сатпаева, 5", phone="+7 701 000 00 00",
    )
    employment = SimpleNamespace(
        position_ru="менеджер по продажам", department="отдел продаж",
        start_date=date(2026, 8, 5), salary=Decimal("300000"),
        probation_months=3,
        hours_per_week=Decimal("40"), work_time_from="09:00", work_time_to="18:00",
        lunch_from="13:00", lunch_to="14:00", days_off="суббота, воскресенье",
        order_number="15", order_date=date(2026, 8, 5),
        contract_number="15", contract_date=date(2026, 8, 5),
        application_date=date(2026, 8, 4),
    )
    return company, employee, employment


def _docx_text(buffer) -> str:
    """Extract all text (paragraphs + table cells) from a rendered .docx."""
    xml = zipfile.ZipFile(buffer).read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    import html
    return html.unescape(text)


def test_order_context_key_fields():
    company, employee, employment = sample_entities()
    ctx = build_order_context(company, employee, employment, hr_responsible_fio="Петрова А.А.")

    assert ctx["employee"]["fio_accusative_upper"] == "КЛИМОВА ВАСИЛИЯ АЛЕКСАНДРОВИЧА"
    assert ctx["employee"]["fio_dative"] == "Климову Василию Александровичу"
    assert ctx["employee"]["fio_genitive"] == "Климова Василия Александровича"
    assert ctx["employment"]["salary_figures"] == "300 000"
    assert ctx["employment"]["salary_words_ru"] == "триста тысяч"
    assert ctx["employment"]["probation_months_words"] == "три"
    # start 05.08.2026 + 3 мес − 1 день = 04.11.2026
    assert ctx["employment"]["probation_end_date_short"] == "04.11.2026"
    assert ctx["employment"]["start_date_words"] == "05 августа 2026 года"
    assert ctx["company"]["signer_fio_short"] == "Иванов И.И."
    assert ctx["contract"]["date_short"] == "05.08.2026"
    assert ctx["application"]["date_short"] == "04.08.2026"


def test_render_prikaz_fills_all_placeholders():
    company, employee, employment = sample_entities()
    ctx = build_order_context(company, employee, employment, hr_responsible_fio="Петрова А.А.")
    buffer = render_template("prikaz_o_prieme.docx", ctx)
    text = _docx_text(buffer)

    # No unresolved jinja/docxtpl tags remain.
    assert "{{" not in text and "{%" not in text

    for needle in [
        "ПРИНЯТЬ КЛИМОВА ВАСИЛИЯ АЛЕКСАНДРОВИЧА",
        "ИИН 900715312346",
        "менеджер по продажам",
        "в отдел продаж",
        "с 05 августа 2026 года",
        "300 000 (триста тысяч) тенге",
        "3 (три) месяца с 05.08.2026 по 04.11.2026",
        "40-часовая рабочая неделя, с 09:00 до 18:00",
        "единую систему учёта трудовых договоров",   # ЕСУТД clause present
        "ознакомить работника под роспись",
        "трудовой договор № 15 от 05.08.2026",
        "заявление Климова Василия Александровича от 04.08.2026",
        "Петрова А.А.",
    ]:
        assert needle in text, f"missing in rendered doc: {needle!r}"


def test_render_without_probation_uses_else_branch():
    company, employee, employment = sample_entities()
    employment.probation_months = 0
    ctx = build_order_context(company, employee, employment)
    text = _docx_text(render_template("prikaz_o_prieme.docx", ctx))
    assert "без испытательного срока" in text
    assert "испытательный срок продолжительностью" not in text


def test_output_filename():
    assert output_filename("Климов", "Василий", "Александрович", "ПриказПриём", date(2026, 8, 5)) == \
        "Климов_ВА_ПриказПриём_2026-08-05.docx"


def test_deductions_exact_texts():
    ctx = build_deductions_context(["base_30_mrp", "social_882"], date(2026, 8, 1))
    assert ctx["list"][0].startswith("Базовый налоговый вычет в размере 30-кратного")
    assert ctx["list"][1].startswith("Социальный налоговый вычет в размере 882-кратного")
    assert ctx["has_social"] is True
    assert ctx["apply_from_words"] == "01 августа 2026 года"

    ctx2 = build_deductions_context(["social_payments"], date(2026, 8, 1))
    assert ctx2["has_social"] is False
