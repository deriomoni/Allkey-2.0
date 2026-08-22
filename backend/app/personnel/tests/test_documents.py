"""Render tests for the rest of the document package + the ZIP bundle + Excel опись
parsing. Contexts are built from lightweight namespaces / Pydantic bodies (the
module is stateless — no DB)."""
import asyncio
import html
import re
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.personnel.context import (
    build_matotvet_context, build_nekonkurencii_context, build_akt_context, build_perechen_context,
    build_trudovoy_context, build_polozhenie_pd_context, build_prikaz_pd_context,
)
from app.personnel.generator import render_template, render_bytes, build_zip
from app.personnel import router as R
from app.personnel import schemas as s
from app.personnel.tests.test_generation import sample_entities

FAKE_USER = SimpleNamespace(id=1, email="t@t.kz", full_name="Кадровик", role="employee", is_active=True)


def run(coro):
    return asyncio.run(coro)


def _docx_text(buffer) -> str:
    xml = zipfile.ZipFile(buffer).read("word/document.xml").decode("utf-8")
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))


NC = SimpleNamespace(
    number="3", doc_date=date(2026, 8, 5),
    term_noncompete="6 (шесть) месяцев", term_nonsolicit="12 (двенадцать) месяцев",
    term_confidential="3 (три) года", territory="Республики Казахстан",
    activity="бухгалтерские услуги", competitors="ТОО «Конкурент»", penalty="500 000 тенге",
)


def test_render_matotvet():
    company, employee, employment = sample_entities()
    ctx = build_matotvet_context(company, employee, employment, SimpleNamespace(number="7", doc_date=date(2026, 8, 5)))
    text = _docx_text(render_template("dogovor_matotvetstvennost.docx", ctx))
    assert "{{" not in text and "{%" not in text
    assert "ДОГОВОР № 7" in text
    assert "05 августа 2026 года" in text
    assert "Климов Василий Александрович" in text


def test_render_nekonkurencii():
    company, employee, employment = sample_entities()
    ctx = build_nekonkurencii_context(company, employee, employment, NC)
    text = _docx_text(render_template("dogovor_nekonkurencii.docx", ctx))
    assert "{{" not in text and "{%" not in text
    assert "6 (шесть) месяцев" in text
    assert "500 000 тенге" in text          # penalty clause rendered


def test_render_akt_with_totals():
    company, employee, employment = sample_entities()
    inventory = [
        SimpleNamespace(name="Ноутбук Dell", code="НВ-001", unit="шт", qty=Decimal("2"), price=Decimal("350000")),
        SimpleNamespace(name="Принтер HP", code="НВ-002", unit="шт", qty=Decimal("1"), price=Decimal("90000")),
    ]
    act = SimpleNamespace(
        number="1", doc_date=date(2026, 8, 5), basis="приказ № 14 от 05.08.2026", notes="",
        commission=[SimpleNamespace(position="Главный бухгалтер", fio_short="Петрова А.А."),
                    SimpleNamespace(position="Кладовщик", fio_short="Сидоров С.С.")],
    )
    # вариант 1: со ссылкой на договор о матответственности
    ctx = build_akt_context(company, employee, employment, act, inventory,
                            SimpleNamespace(number="7", doc_date=date(2026, 8, 5)))
    text = _docx_text(render_template("akt_priema_peredachi.docx", ctx))
    assert "{{" not in text and "{%" not in text
    for needle in ["Ноутбук Dell", "Принтер HP", "Петрова А.А.", "Сидоров С.С.",
                   "приказ № 14 от 05.08.2026"]:
        assert needle in text
    # totals computed: 2*350000 + 1*90000 = 790000
    assert "790 000 (семьсот девяносто тысяч) тенге" in text

    # вариант 2: без договора (liability пустой) — акт всё равно рендерится
    text2 = _docx_text(render_template(
        "akt_priema_peredachi.docx",
        build_akt_context(company, employee, employment, act, inventory,
                          SimpleNamespace(number="", doc_date=None))))
    assert "{{" not in text2 and "{%" not in text2 and "Ноутбук Dell" in text2


def test_render_perechen():
    company, _, _ = sample_entities()
    perechen = SimpleNamespace(
        number="8", doc_date=date(2026, 8, 5), responsible_fio="Ахметов Асхат Болатович",
        responsible_position="главного бухгалтера", control="оставляю за собой",
        positions=[SimpleNamespace(name="Бухгалтер", reason="доступ к клиентской базе"),
                   SimpleNamespace(name="Менеджер", reason="условия договоров и скидки")],
        acquainted=[SimpleNamespace(position="Бухгалтер", fio_short="Климов В.А.")],
    )
    ctx = build_perechen_context(company, perechen, NC)
    text = _docx_text(render_template("prikaz_perechen_nekonkurencii.docx", ctx))
    assert "{{" not in text and "{%" not in text
    for needle in ["Бухгалтер", "доступ к клиентской базе", "Климов В.А.", "6 (шесть) месяцев",
                   "Ахметова Асхата Болатовича"]:  # responsible_fio in accusative
        assert needle in text


def _td(kind, salary_kind="gross", **extra):
    company = s.CompanyBase(
        name_ru="ТОО «Ромашка»", name_kk="«Ромашка» ЖШС", bin="150640001237",
        city="Алматы", legal_address="ул. Абая, 1", address_kz="Абай к-сі, 1",
        director_fio_ru="Иванов Иван Иванович", director_fio_kk="Иванов Иван Иванович",
        signatory_position="Директор", signer_position_kz="Директор", acts_on_basis="Устава",
    )
    employee = s.EmployeeIn(
        last_name="Климов", first_name="Василий", middle_name="Александрович",
        fio_full_kz="Климов Василий Александрович", iin="900715312346", gender="male",
        document_type="id_card", document_number="012345678", document_issued_by="МВД РК",
        id_document_kz="жеке куәлік № 012345678", actual_address="г. Алматы",
    )
    employment = s.EmploymentIn(
        position_ru="менеджер", position_kk="менеджер", workplace="офис", workplace_kz="кеңсе",
        conditions="нормальными", start_date=date(2026, 8, 5), salary=Decimal("300000"),
        salary_kind=salary_kind,
        probation_months=3, hours_per_day=Decimal("8"), hours_per_week=Decimal("40"),
        days_off="суббота, воскресенье", vacation_days=24,
    )
    contract = s.ContractIn(number="21", doc_date=date(2026, 8, 5), kind=kind, confidential_years="3", **extra)
    req = s.TrudovoyRequest(company=company, employee=employee, employment=employment, contract=contract)
    ctx = build_trudovoy_context(req.company, req.employee, req.employment, req.contract)
    return _docx_text(render_template("trudovoy_dogovor.docx", ctx))


def test_trudovoy_indefinite_bilingual():
    text = _td("indefinite")
    assert "{{" not in text and "{%" not in text
    for needle in [
        "ТРУДОВОЙ ДОГОВОР № 21", "ЕҢБЕК ШАРТЫ",
        "05 августа 2026 года", "05 тамыз 2026 жыл",
        "300 000 (триста тысяч)", "300 000 (үш жүз мың)",
        "сенбі, жексенбі", "қалыпты",
        "Договор заключён на неопределённый срок", "белгіленбеген мерзімге",
        "3 (три) месяца", "3 (үш) ай",
    ]:
        assert needle in text, needle


def test_trudovoy_fixed_term():
    text = _td("fixed", term_count=1, term_unit="year", end_date=date(2027, 8, 4))
    assert "{{" not in text and "{%" not in text
    assert "1 (один) год" in text and "1 (бір) жыл" in text
    assert "04 августа 2027 года" in text and "04 тамыз 2027 жыл" in text


def test_trudovoy_salary_kind_changes_wording():
    # Сумма подставляется как есть (300 000 в обоих), но формулировка 4.1 разная.
    gross = _td("indefinite", salary_kind="gross")
    net = _td("indefinite", salary_kind="net")
    assert "{%" not in gross and "{%" not in net
    assert "300 000 (триста тысяч)" in gross and "300 000 (триста тысяч)" in net
    assert "должностной оклад" in gross          # к начислению
    assert "должностной оклад" not in net        # на руки — иная формулировка
    assert gross != net
    # Приложение № 1 об окладе убрано полностью
    assert "Приложение № 1" not in gross and "Приложение №1" not in gross


def test_trudovoy_kk_derived_without_kk_inputs():
    # Без единого казахского поля работника/условий: ФИО копируется из русского,
    # id-документ собирается из структурных полей, место работы — юр. адрес компании.
    company = s.CompanyBase(name_ru="ТОО «Ромашка»", name_kk="«Ромашка» ЖШС", bin="150640001237",
                            city="Алматы", legal_address="ул. Абая, 1", address_kz="Абай к-сі, 1",
                            director_fio_ru="Иванов Иван Иванович", signer_position_kz="Директор")
    employee = s.EmployeeIn(last_name="Климов", first_name="Василий", middle_name="Александрович",
                            iin="900715312346", gender="male", document_type="id_card",
                            document_number="012345678", document_issued_by="ІІМ РК",
                            document_issue_date=date(2015, 3, 20))
    employment = s.EmploymentIn(position_ru="менеджер", position_kk="менеджер",
                                salary=Decimal("300000"), start_date=date(2026, 8, 5))
    contract = s.ContractIn(number="21", doc_date=date(2026, 8, 5), kind="indefinite")
    c = build_trudovoy_context(company, employee, employment, contract)
    assert c["employee"]["fio_full_kz"] == c["employee"]["fio_full"]        # ФИО из русского
    assert c["company"]["signer_fio_kz"] == "Иванов Иван Иванович"
    assert "жеке куәлік № 012345678" in c["employee"]["id_document_kz"] and "берген" in c["employee"]["id_document_kz"]
    assert c["employment"]["workplace"] == "ул. Абая, 1"                    # = юр. адрес
    assert c["employment"]["workplace_kz"] == "Абай к-сі, 1"                # = address_kz компании
    assert c["company"]["name_full_kz"] == "«Ромашка» ЖШС"


def test_trudovoy_task_and_substitute():
    t1 = _td("task", task="разработка сайта", task_kz="сайт әзірлеу")
    assert "{%" not in t1 and "разработка сайта" in t1 and "сайт әзірлеу" in t1
    t2 = _td("substitute")
    assert "{%" not in t2 and "замещения временно отсутствующего" in t2


def test_render_polozhenie_pd():
    company, _, _ = sample_entities()
    policy = SimpleNamespace(order_number="12", doc_date=date(2026, 8, 6))
    text = _docx_text(render_template("polozhenie_personalnye_dannye.docx",
                                      build_polozhenie_pd_context(company, policy)))
    assert "{{" not in text and "{%" not in text
    assert "ТОО «Ромашка»" in text and "06.08.2026" in text


def test_render_prikaz_pd():
    company, _, _ = sample_entities()
    policy = SimpleNamespace(
        order_number="12", doc_date=date(2026, 8, 6),
        responsible_fio="Ахметов Асхат Болатович", responsible_position="главный бухгалтер",
        deadline=date(2026, 8, 10), control="оставляю за собой",
        acquainted=[SimpleNamespace(position="Главный бухгалтер", fio_short="Петрова А.А."),
                    SimpleNamespace(position="Кадровик", fio_short="Сидоров С.С.")],
    )
    text = _docx_text(render_template("prikaz_otvetstvennyy_pd.docx",
                                      build_prikaz_pd_context(company, policy)))
    assert "{{" not in text and "{%" not in text
    for needle in ["Ахметова Асхата Болатовича", "главного бухгалтера",
                   "06 августа 2026 года", "10.08.2026", "Петрова А.А.", "Сидоров С.С."]:
        assert needle in text, needle


def test_salary_rejects_kopecks():
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc:
        s.EmploymentIn(position_ru="менеджер", salary="347850,50")
    assert "целыми тенге" in str(exc.value)
    # целое принимается: число, строка, строка с пробелами
    assert s.EmploymentIn(salary=300000).salary == 300000
    assert s.EmploymentIn(salary="347 850").salary == 347850
    assert s.EmploymentIn().salary == 0


def test_kk_dictionaries():
    from app.personnel import kk_dictionaries as kkd
    assert kkd.kk_city("Алматы") == "Алматы"
    assert kkd.kk_city("Караганда") == "Қарағанды"
    assert kkd.kk_days_off("суббота, воскресенье") == "сенбі, жексенбі"
    assert kkd.kk_conditions("нормальными") == "қалыпты"
    assert kkd.kk_basis("Устава") == "Жарғы"


def test_build_zip_bundles_docx():
    company, employee, employment = sample_entities()
    from app.personnel.context import build_order_context
    prikaz = render_bytes("prikaz_o_prieme.docx", build_order_context(company, employee, employment))
    matotvet = render_bytes("dogovor_matotvetstvennost.docx",
                            build_matotvet_context(company, employee, employment,
                                                   SimpleNamespace(number="7", doc_date=date(2026, 8, 5))))
    archive = build_zip([("prikaz.docx", prikaz), ("matotvet.docx", matotvet)])
    names = zipfile.ZipFile(archive).namelist()
    assert sorted(names) == ["matotvet.docx", "prikaz.docx"]


# --- package endpoint (stateless, direct async call) ---

def _pkg(documents, **extra):
    return s.PackageRequest(
        company=s.CompanyBase(name_ru="ТОО «Астана»", bin="150640001237", city="Астана",
                              director_fio_ru="Ахметов Асхат Болатович"),
        employee=s.EmployeeIn(last_name="Оспанов", first_name="Данияр", middle_name="Маратович",
                              iin="900715312346", gender="male"),
        employment=s.EmploymentIn(position_ru="бухгалтер", salary=Decimal("450000"),
                                  order_number="1", order_date=date(2026, 8, 5)),
        documents=documents, **extra,
    )


async def _zip_names(req):
    resp = await R.generate_package(req, user=FAKE_USER)
    chunks = [c if isinstance(c, bytes) else c.encode() async for c in resp.body_iterator]
    return zipfile.ZipFile(BytesIO(b"".join(chunks))).namelist()


def test_package_bundles_selected_documents():
    names = run(_zip_names(_pkg(["prikaz", "matotvet"], liability=s.LiabilityIn(number="7", doc_date=date(2026, 8, 5)))))
    assert len(names) == 2
    assert any("Приказ" in n for n in names) and any("Договор" in n for n in names)


def test_package_pd_and_deductions():
    # ПД-пакет + заявление на вычеты: заход, который подключает фронт
    names = run(_zip_names(_pkg(
        ["zayavlenie", "polozhenie_pd", "prikaz_pd"],
        deductions=["base_30_mrp"],
        apply_from=date(2026, 9, 1),
        policy=s.PolicyIn(order_number="60", doc_date=date(2026, 8, 5),
                          responsible_fio="Ахметов Асхат Болатович", responsible_position="директор",
                          acquainted=[s.CommissionMemberIn(position="бухгалтер", fio_short="Оспанов Д.М.")]),
    )))
    assert len(names) == 3
    assert any("Заявлен" in n for n in names)
    assert any("Положен" in n for n in names)
    assert any("Приказ" in n for n in names)


def test_package_td_fixed_term():
    names = run(_zip_names(_pkg(
        ["td"],
        contract=s.ContractIn(number="47", doc_date=date(2026, 8, 5), kind="fixed",
                              term_count=1, term_unit="year", end_date=date(2027, 8, 4)),
    )))
    assert len(names) == 1
    assert any("Трудов" in n for n in names)


def test_package_soglasie():
    names = run(_zip_names(_pkg(
        ["soglasie"],
        consent=s.SoglasieIn(doc_date=date(2026, 8, 5),
                             responsible_position="менеджер по персоналу", responsible_fio="Ахметова А.С.",
                             recipients=[s.RecipientIn(name="АО «Народный Банк»", bin="940140000385",
                                                       purpose="выплата зарплаты", scope="ФИО, ИИН, счёт")]),
    )))
    assert len(names) == 1
    assert any("Согласие" in n for n in names)


def test_package_soglasie_needs_consent():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg(["soglasie"]), user=FAKE_USER))  # no consent
    assert exc.value.status_code == 400


def test_package_noncompete_and_perechen():
    names = run(_zip_names(_pkg(
        ["nekonkurencii", "perechen"],
        noncompete=s.NonCompeteIn(number="НК-47", doc_date=date(2026, 8, 5),
                                  term_noncompete="6 (шесть) месяцев", penalty="500 000 тенге"),
        perechen=s.PerechenIn(number="59", doc_date=date(2026, 8, 5),
                              responsible_fio="Ахметов Асхат Болатович", responsible_position="директор",
                              positions=[s.PerechenPositionIn(name="менеджер", reason="доступ к базе клиентов")]),
    )))
    assert len(names) == 2
    assert any("Неконкуренц" in n for n in names)
    assert any("Перечень" in n for n in names)


def test_package_td_needs_contract():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg(["td"]), user=FAKE_USER))  # no contract
    assert exc.value.status_code == 400


def test_package_zayavlenie_needs_deductions():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg(["zayavlenie"], deductions=[]), user=FAKE_USER))
    assert exc.value.status_code == 400


def test_package_social_deduction_needs_document():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg(["zayavlenie"], deductions=["base_30_mrp", "social_882"]), user=FAKE_USER))
    assert exc.value.status_code == 400


def test_package_social_deduction_with_document_ok():
    names = run(_zip_names(_pkg(["zayavlenie"], deductions=["base_30_mrp", "social_882"],
                                social_document="справка ВТЭК № 5 от 10.01.2026")))
    assert len(names) == 1 and any("Заявлен" in n for n in names)


def test_package_missing_input_rejected():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg(["matotvet"]), user=FAKE_USER))  # no liability
    assert exc.value.status_code == 400


def test_package_no_documents_rejected():
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(_pkg([]), user=FAKE_USER))
    assert exc.value.status_code == 400


# --- Excel опись parsing ---

def _xlsx(rows) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _parse(rows, **mapping):
    # Direct call: Form params default to FieldInfo, so pass them explicitly.
    upload = UploadFile(filename="opis.xlsx", file=BytesIO(_xlsx(rows)))
    kw = dict(header_row=None, col_name=None, col_qty=None, col_price=None, col_code=None, col_unit=None)
    kw.update(mapping)
    return run(R.parse_inventory(file=upload, _user=FAKE_USER, **kw))


def test_parse_inventory_standard_header():
    resp = _parse([
        ["Наименование", "Код", "Ед.изм.", "Кол-во", "Цена"],
        ["Ноутбук", "НВ-1", "шт", 2, 350000],
        ["Принтер", "НВ-2", "шт", 1, 90000],
        ["", "", "", "", ""],  # blank row ignored
    ])
    assert resp.status == "parsed" and len(resp.items) == 2
    assert resp.items[0].name == "Ноутбук" and resp.items[0].qty == Decimal("2")
    assert resp.items[1].price == Decimal("90000")


def test_parse_inventory_synonyms():
    # accountant-style column names
    resp = _parse([
        ["Номенклатура", "Инв. номер", "Ед.", "Кол-во", "Цена, тг"],
        ["Стол", "ИН-5", "шт", "3", "45 000"],
    ])
    assert resp.status == "parsed" and len(resp.items) == 1
    assert resp.items[0].name == "Стол" and resp.items[0].qty == Decimal("3")
    assert resp.items[0].price == Decimal("45000")


def test_parse_inventory_1c_preamble():
    # header is not the first row (org name / period / blank above it)
    resp = _parse([
        ["ТОО «Ромашка»"],
        ["Период: 01.08.2026 - 05.08.2026"],
        [],
        ["Наименование", "Кол-во", "Цена"],
        ["Ноутбук", 2, 350000],
        ["Принтер", 1, 90000],
    ])
    assert resp.status == "parsed" and resp.header_row == 3 and len(resp.items) == 2


def test_parse_inventory_needs_mapping():
    resp = _parse([["Штрих", "Единиц", "Деньги"], ["Ноутбук", 2, 350000]])
    assert resp.status == "needs_mapping"
    assert [c.title for c in resp.columns] == ["Штрих", "Единиц", "Деньги"]
    assert resp.columns[0].samples == ["Ноутбук"]


def test_parse_inventory_explicit_mapping():
    resp = _parse(
        [["Мои", "Данные", "Здесь"], ["Ноутбук", "2", "350000"]],
        header_row=0, col_name=0, col_qty=1, col_price=2,
    )
    assert resp.status == "parsed" and len(resp.items) == 1
    assert resp.items[0].name == "Ноутбук" and resp.items[0].price == Decimal("350000")


def test_generation_rejects_invalid_iin():
    # ИИН 745820400487: месяц рождения «58» не существует → пакет не формируется.
    req = _pkg(["prikaz"])
    req.employee = req.employee.model_copy(update={"iin": "745820400487"})
    with pytest.raises(HTTPException) as exc:
        run(R.generate_package(req, user=FAKE_USER))
    assert exc.value.status_code == 400


def test_prikaz_department_phrase_and_empty():
    from app.personnel.context import build_order_context
    company = s.CompanyBase(name_ru="ТОО", bin="150640001237", director_fio_ru="Иванов Иван Иванович")
    employee = s.EmployeeIn(last_name="Оспан", first_name="Ербол", iin="950313300574", gender="male")
    with_dept = build_order_context(company, employee,
                                    s.EmploymentIn(position_ru="менеджер", department="Отдел продаж", salary=300000))
    assert with_dept["employment"]["department"] == "подразделение «Отдел продаж»"
    without = build_order_context(company, employee,
                                  s.EmploymentIn(position_ru="менеджер", department="", salary=300000))
    assert without["employment"]["department"] == ""      # пусто → строка не выводится, без «Основное»
