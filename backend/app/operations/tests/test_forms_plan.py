"""«Формы» экрана «Компании» и экспорта = tax.forms ∪ план на текущий год (владелец 24.11.2026)."""
import datetime as dt
import io

from openpyxl import load_workbook

from app.operations.models import OpsCompany, OpsCompanyReport
from app.operations.tests.test_cabinet_queue import env  # noqa: F401  (фикстура: alfa, beta, nokey — живые; old — архив)

Y = str(dt.date.today().year)


def _add_plan(db, slug, form, period, status="due", source="plan"):
    c = db.query(OpsCompany).filter_by(slug=slug).one()
    db.add(OpsCompanyReport(company_id=c.id, form=form, period=period, status=status, source=source))
    db.commit()


def test_list_forms_union_plan_and_marker(env):  # noqa: F811
    client, hdr, ids, db, _ = env
    a = db.query(OpsCompany).filter_by(slug="alfa").one()
    a.card_json = {**a.card_json, "tax": {"forms": [{"form": "200.00", "source": "import_xlsx"}]}}
    db.commit()
    _add_plan(db, "alfa", "220.00", Y)
    _add_plan(db, "alfa", "200.00", f"{Y}-Q4", status="clarify")
    _add_plan(db, "alfa", "ЕСУТД", "не описан")
    _add_plan(db, "alfa", "910.00", "2025-H2")                     # прошлый год — не берётся
    _add_plan(db, "alfa", "300.00", f"{Y}-Q4", status="not_required")  # «не требуется» — не берётся
    _add_plan(db, "alfa", "100.00", f"{Y}", source="import_xlsx")   # история — не план
    _add_plan(db, "old", "100.00", Y)
    for who in ("owner", "staff"):
        items = {i["slug"]: i for i in client.get("/api/ops/companies", headers=hdr[who]).json()["items"]}
        assert items["alfa"]["forms"] == ["200.00", "220.00", "ЕСУТД"]
        assert items["alfa"]["plan_missing"] is False
        assert items["beta"]["forms"] == [] and items["beta"]["plan_missing"] is True   # живая без плана
        assert items["old"]["plan_missing"] is False                                    # архив — без пометки
    # карточка — тот же список
    assert client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["owner"]).json()["forms"] == ["200.00", "220.00", "ЕСУТД"]
    # tax.forms карточки не тронут (импорт форм работает с ним)
    db.refresh(a)
    assert [f["form"] for f in a.card_json["tax"]["forms"]] == ["200.00"]


def test_export_uses_union_and_flags(env):  # noqa: F811
    client, hdr, ids, db, _ = env
    _add_plan(db, "alfa", "220.00", Y)
    r = client.post("/api/ops/companies/export", headers=hdr["owner"], json={"ids": [ids["alfa"], ids["beta"]]})
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    head = [c.value for c in ws[1]]
    rows = {row[0]: dict(zip(head, row)) for row in ws.iter_rows(min_row=2, values_only=True)}
    assert rows["Альфа ТОО"]["Формы"] == "220.00" and rows["Альфа ТОО"]["220.00"] == "да"
    assert rows["Бета ТОО"]["Формы"] == "план не рассчитан" and rows["Бета ТОО"]["220.00"] in (None, "")
