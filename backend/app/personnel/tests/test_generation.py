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

from app.personnel.context import (
    build_order_context, build_deductions_context, build_deduction_application_context,
)
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
    assert ctx["employee"]["fio_genitive"] == "Климова Василия Александровича"
    # оклад, режим и дательный из приказа убраны (место — в ТД/ПВТР)
    assert "fio_dative" not in ctx["employee"]
    assert "salary_figures" not in ctx["employment"] and "days_off" not in ctx["employment"]
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
        "3 (три) месяца с 05.08.2026 по 04.11.2026",
        "штатным расписанием",                         # п.2: оплата по ТД + штатному расписанию
        "единую систему учёта трудовых договоров",     # ЕСУТД clause present
        "ознакомить работника под роспись",
        "трудовой договор № 15 от 05.08.2026",
        "заявление Климова Василия Александровича от 04.08.2026",
        "Петрова А.А.",
    ]:
        assert needle in text, f"missing in rendered doc: {needle!r}"

    # Оклад и режим работы в приказе БОЛЬШЕ НЕ печатаются (место — в ТД/ПВТР).
    assert "тенге" not in text and "рабочая неделя" not in text


def test_render_without_probation_uses_else_branch():
    company, employee, employment = sample_entities()
    employment.probation_months = 0
    ctx = build_order_context(company, employee, employment)
    text = _docx_text(render_template("prikaz_o_prieme.docx", ctx))
    assert "без испытательного срока" in text
    assert "испытательный срок продолжительностью" not in text


def test_render_zayavlenie_vychety_fills_and_loops():
    company, employee, _ = sample_entities()
    ctx = build_deduction_application_context(
        company, employee,
        selection=["base_30_mrp", "social_882"],
        apply_from=date(2026, 8, 1),
        application_date=date(2026, 8, 4),
    )
    text = _docx_text(render_template("zayavlenie_vychety_ipn.docx", ctx))

    assert "{{" not in text and "{%" not in text
    for needle in [
        "ТОО «Ромашка»",
        "БИН 150640001237",
        "Климова Василия Александровича, ИИН 900715312346",   # from: fio_genitive
        "1. Базовый налоговый вычет в размере 30-кратного",    # loop item 1, numbered
        "2. Социальный налоговый вычет в размере 882-кратного",  # loop item 2
        "начиная с августа 2026 года",   # месяц, не дата (ст. 403 НК РК)
        "подтверждающих право на применение социального",       # has_social attachment clause
        "Климов Василий Александрович",                          # signature: fio_full
    ]:
        assert needle in text, f"missing in rendered zayavlenie: {needle!r}"


def _akt_context():
    """Inline context for akt_priema_peredachi.docx. The акт is fed from the form
    (опись + комиссия) which is not built yet, so the context is assembled here to
    prove the template + engine render (table-row loop and paragraph loop)."""
    return {
        "company": {"city": "Алматы", "name_full": "ТОО «Ромашка»", "bin": "150640001237"},
        "liability": {"number": "7", "date_short": "05.08.2026"},
        "items": [
            {"name": "Ноутбук Dell", "code": "НВ-001", "unit": "шт", "qty": 2, "price": "350 000", "sum": "700 000"},
            {"name": "Принтер HP", "code": "НВ-002", "unit": "шт", "qty": 1, "price": "90 000", "sum": "90 000"},
        ],
        "act": {
            "number": "1", "date_words": "05 августа 2026 года",
            "transferor_position": "Директор", "transferor_position_genitive": "Директора",
            "transferor_fio_genitive": "Иванова Ивана Ивановича", "transferor_fio_short": "Иванов И.И.",
            "receiver_position": "менеджер", "receiver_fio_full": "Климов Василий Александрович",
            "receiver_iin": "900715312346", "receiver_fio_short": "Климов В.А.",
            "inventory_date": "05.08.2026", "order_number": "15", "order_date": "05.08.2026",
            "total_figures": "790 000", "total_words": "семьсот девяносто тысяч",
            "items_count": 2, "items_count_words": "два", "notes": "",
            "commission": [
                {"position": "Главный бухгалтер", "fio_short": "Петрова А.А."},
                {"position": "Кладовщик", "fio_short": "Сидоров С.С."},
            ],
        },
    }


def test_render_akt_table_and_commission_loops():
    text = _docx_text(render_template("akt_priema_peredachi.docx", _akt_context()))

    assert "{{" not in text and "{%" not in text
    for needle in [
        "Ноутбук Dell", "НВ-001", "700 000",        # table-row loop, item 1
        "Принтер HP", "НВ-002",                       # table-row loop, item 2
        "Главный бухгалтер", "Петрова А.А.",          # paragraph loop, commission 1
        "Кладовщик", "Сидоров С.С.",                  # paragraph loop, commission 2
        "790 000 (семьсот девяносто тысяч) тенге",
        "Климов Василий Александрович",
    ]:
        assert needle in text, f"missing in rendered akt: {needle!r}"


def test_fio_override_takes_priority():
    from app.personnel.context import current_declensions, build_employee_context
    _, employee, _ = sample_entities()
    employee.fio_genitive_override = "Климова Василия Александровича (ручная правка)"
    decl = current_declensions(employee)
    assert decl["fio_genitive"] == "Климова Василия Александровича (ручная правка)"
    assert decl["fio_dative"] == "Климову Василию Александровичу"      # not overridden → autogen
    ctx = build_employee_context(employee)
    assert ctx["fio_genitive"] == "Климова Василия Александровича (ручная правка)"


def test_salary_words_override_reaches_employment_context():
    # Оклад прописью используется в ТД (не в приказе): правка попадает в контекст
    # найма, а приказ вообще не содержит суммы оклада.
    company, employee, employment = sample_entities()
    employment.salary_words_override = "ноль"  # manual edit of the sum-in-words
    from app.personnel.context import build_employment_context
    assert build_employment_context(employment)["salary_words_ru"] == "ноль"
    order_ctx = build_order_context(company, employee, employment)
    assert "salary_words_ru" not in order_ctx["employment"]
    assert "salary_figures" not in order_ctx["employment"]


def test_output_filename():
    assert output_filename("Климов", "Василий", "Александрович", "ПриказПриём", date(2026, 8, 5)) == \
        "Климов_ВА_ПриказПриём_2026-08-05.docx"


def test_deductions_exact_texts():
    ctx = build_deductions_context(["base_30_mrp", "social_882"], date(2026, 8, 1))
    assert ctx["list"][0].startswith("Базовый налоговый вычет в размере 30-кратного")
    assert ctx["list"][1].startswith("Социальный налоговый вычет в размере 882-кратного")
    assert ctx["has_social"] is True
    assert ctx["apply_from_words"] == "августа 2026 года"

    # социальный вычет с подтверждающим документом — основание попадает в текст
    ctx2 = build_deductions_context(["social_882"], date(2026, 8, 1),
                                    social_document="справка ВТЭК № 5 от 10.01.2026")
    assert "на основании: справка ВТЭК № 5 от 10.01.2026" in ctx2["list"][0]
    assert ctx2["has_social"] is True

    # вычет соц.платежей убран из справочника — незнакомый ключ просто отбрасывается
    ctx3 = build_deductions_context(["social_payments"], date(2026, 8, 1))
    assert ctx3["list"] == [] and ctx3["has_social"] is False
