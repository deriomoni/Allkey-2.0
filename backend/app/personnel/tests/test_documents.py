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
        number="1", doc_date=date(2026, 8, 5), inventory_date=date(2026, 8, 5),
        order_number="15", order_date=date(2026, 8, 5), notes="",
        commission=[SimpleNamespace(position="Главный бухгалтер", fio_short="Петрова А.А."),
                    SimpleNamespace(position="Кладовщик", fio_short="Сидоров С.С.")],
    )
    ctx = build_akt_context(company, employee, employment, act, inventory,
                            SimpleNamespace(number="7", doc_date=date(2026, 8, 5)))
    text = _docx_text(render_template("akt_priema_peredachi.docx", ctx))
    assert "{{" not in text and "{%" not in text
    for needle in ["Ноутбук Dell", "Принтер HP", "Петрова А.А.", "Сидоров С.С."]:
        assert needle in text
    # totals computed: 2*350000 + 1*90000 = 790000
    assert "790 000 (семьсот девяносто тысяч) тенге" in text


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


def test_parse_inventory_with_header():
    data = _xlsx([
        ["Наименование", "Код", "Ед.изм.", "Кол-во", "Цена"],
        ["Ноутбук", "НВ-1", "шт", 2, 350000],
        ["Принтер", "НВ-2", "шт", 1, 90000],
        ["", "", "", "", ""],  # blank row ignored
    ])
    upload = UploadFile(filename="opis.xlsx", file=BytesIO(data))
    resp = run(R.parse_inventory(file=upload, _user=FAKE_USER))
    assert len(resp.items) == 2
    assert resp.items[0].name == "Ноутбук"
    assert resp.items[0].qty == Decimal("2")
    assert resp.items[1].price == Decimal("90000")
