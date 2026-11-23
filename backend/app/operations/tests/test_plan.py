"""План отчётов (reports/plan-2026.csv) → ops_company_reports, решения по «уточнить», экспорт."""
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.database import Base, get_db
import app.users.models  # noqa: F401
from app.users.models import User
from app.operations import access, plan as plan_mod
from app.operations.access import OpsGateMiddleware
from app.operations.config import get_ops_settings
from app.operations.models import OpsCardProposal, OpsCompany, OpsCompanyReport, UserRoleAssignment
from app.operations.plan import norm_period, read_plan_csv
from app.operations.router import ext_router, router

HEADER = "company_slug,bin,form,period,due_date,status,clarify_reason,basis,info_source,regime,vat,registry_sheet\n"
CSV = HEADER + (
    "alfa,111111111111,200.00,4 кв. 2026,15.02.2027,ожидается,,календарь №2а,правовая форма,ОУР,да,200.00\n"
    "alfa,111111111111,300.00,4 кв. 2026,15.02.2027,уточнить,НДС не подтверждён,календарь №1,НДС: файл,ОУР,не установлено,300.00\n"
    "alfa,111111111111,910.00,2 п/г 2026,15.02.2027,ожидается,,календарь №3,режим,СНР,нет,ФНО910\n"
    "beta,222222222222,700.00,2026,31.03.2027,уточнить,транспорт не подтверждён,календарь №7,TODO,ОУР,да,700.00\n"
    "ghost,333333333333,200.00,4 кв. 2026,15.02.2027,ожидается,,x,y,ОУР,да,200.00\n"
)
CARD_ALFA = {"name": "Альфа", "tax": {"forms": [{"form": "300.00", "source": "import_xlsx"}]}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    owner = User(email="owner@t.kz", hashed_password="x", full_name="Владелец", role="admin", is_active=True)
    emp = User(email="emp@t.kz", hashed_password="x", full_name="Сотрудник", role="employee", is_active=True)
    db.add_all([owner, emp])
    db.commit()
    alfa = OpsCompany(slug="alfa", name="Альфа ТОО", bin="111111111111", card_json=CARD_ALFA, active=True)
    beta = OpsCompany(slug="beta", name="Бета ТОО", bin="222222222222", card_json={"name": "Бета"}, active=True)
    db.add_all([alfa, beta])
    db.commit()
    db.add(UserRoleAssignment(user_id=owner.id, role="admin"))
    # История из реестра владельца — та же компания/форма/период, что в плане (910.00, 2026-H2).
    db.add(OpsCompanyReport(company_id=alfa.id, form="910.00", period="2026-H2", status="submitted",
                            raw_value="сдано", source="import_xlsx"))
    db.add(OpsCompanyReport(company_id=alfa.id, form="200.00", period="2026-Q3", status="accepted",
                            raw_value="принято", source="import_xlsx"))
    db.commit()

    repo = tmp_path / "arty"
    (repo / "reports").mkdir(parents=True)
    (repo / "reports" / "plan-2026.csv").write_text(CSV, encoding="utf-8")
    (repo / "reports" / "discrepancies-2026-11-23.csv").write_text(
        'company_slug,company,discrepancy,source\nalfa,Альфа ТОО,"701.00 в реестре, отменена",календарь §0\n',
        encoding="utf-8")
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(repo))

    app = FastAPI()
    app.add_middleware(OpsGateMiddleware, session_factory=Session)
    app.include_router(ext_router)
    app.include_router(router)

    def _get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr(access, "SessionLocal", Session)
    client = TestClient(app, raise_server_exceptions=False)

    def hdr(user):
        return {"Authorization": "Bearer " + create_access_token({"sub": user.email})}

    yield client, hdr(owner), hdr(emp), Session
    db.close()


def test_norm_period():
    assert norm_period("4 кв. 2026") == "2026-Q4"
    assert norm_period("2 п/г 2026") == "2026-H2"
    assert norm_period("2026") == "2026"
    assert norm_period("по запросу") == "по запросу"


def test_load_keeps_history_and_is_idempotent(env):
    client, owner, _, Session = env
    r = client.post("/api/ops/reports/plan/load", headers=owner).json()
    assert r == {"created": 3, "updated": 0, "conflicts_with_history": 1, "unknown_company": 1, "invalid": 0}
    db = Session()
    hist = db.query(OpsCompanyReport).filter_by(source="import_xlsx").all()
    assert sorted((h.form, h.period, h.status) for h in hist) == [
        ("200.00", "2026-Q3", "accepted"), ("910.00", "2026-H2", "submitted")]
    plan = db.query(OpsCompanyReport).filter_by(source="plan").all()
    assert len(plan) == 3
    # привязка по slug: строка beta — у Беты, со своим сроком и причиной
    b = next(p for p in plan if p.form == "700.00")
    assert b.company_id == db.query(OpsCompany).filter_by(slug="beta").one().id
    assert (b.period, b.status, b.due_date) == ("2026", "clarify", "31.03.2027")
    assert b.plan_json["clarify_reason"] == "транспорт не подтверждён"
    r2 = client.post("/api/ops/reports/plan/load", headers=owner).json()
    assert r2["created"] == 0 and r2["updated"] == 3
    assert db.query(OpsCompanyReport).count() == 5


def test_list_and_counters(env):
    client, owner, _, _ = env
    client.post("/api/ops/reports/plan/load", headers=owner)
    data = client.get("/api/ops/reports/plan", headers=owner).json()
    c = data["counters"]
    assert (c["total"], c["due"], c["clarify"]) == (3, 1, 2)
    # Бета: только «уточнить» → компания без форм
    assert c["companies_without_forms"] == 1
    row = next(i for i in data["items"] if i["form"] == "300.00")
    assert (row["company"], row["period"], row["regime"], row["vat"]) == ("Альфа ТОО", "4 кв. 2026", "ОУР", "не установлено")


def test_decision_writes_row_and_proposal_not_card(env):
    client, owner, _, Session = env
    client.post("/api/ops/reports/plan/load", headers=owner)
    items = client.get("/api/ops/reports/plan", headers=owner).json()["items"]
    vat = next(i for i in items if i["form"] == "300.00")
    tr = next(i for i in items if i["form"] == "700.00")
    url = "/api/ops/reports/{}/decision"
    assert client.post(url.format(vat["id"]), headers=owner,
                       json={"decision": "confirmed", "basis": ""}).status_code == 400
    r = client.post(url.format(vat["id"]), headers=owner,
                    json={"decision": "confirmed", "basis": "КГД: плательщик НДС"})
    assert r.status_code == 200 and r.json()["status"] == "due"
    r = client.post(url.format(tr["id"]), headers=owner, json={"decision": "not_required", "basis": "авто нет"})
    assert r.json()["status"] == "not_required"
    # повторно — нельзя
    assert client.post(url.format(tr["id"]), headers=owner,
                       json={"decision": "confirmed", "basis": "передумал"}).status_code == 409
    db = Session()
    props = db.query(OpsCardProposal).order_by(OpsCardProposal.id).all()
    assert [(p.field_path, p.status, p.new_value["action"], p.new_value["form"]) for p in props] == [
        ("tax.forms", "pending", "add_form", "300.00"), ("tax.forms", "pending", "not_required", "700.00")]
    assert props[0].old_value == {"form": "300.00", "source": "import_xlsx"}
    assert props[0].origin == f"report:{vat['id']}" and props[0].proposed_by == "owner@t.kz"
    # карточка не изменилась
    assert db.query(OpsCompany).filter_by(slug="alfa").one().card_json == CARD_ALFA
    row = db.get(OpsCompanyReport, vat["id"])
    assert (row.decision, row.decision_basis, row.decided_by) == ("confirmed", "КГД: плательщик НДС", "owner@t.kz")
    # перезагрузка плана решение не сбрасывает
    client.post("/api/ops/reports/plan/load", headers=owner)
    db.expire_all()
    assert db.get(OpsCompanyReport, vat["id"]).status == "due"
    c = client.get("/api/ops/reports/plan", headers=owner).json()["counters"]
    assert (c["due"], c["clarify"], c["not_required"], c["companies_without_forms"]) == (2, 0, 1, 1)


def test_discrepancies(env):
    client, owner, emp, _ = env
    d = client.get("/api/ops/reports/discrepancies", headers=owner).json()
    assert d["file"] == "reports/discrepancies-2026-11-23.csv"
    assert d["items"] == [{"company_slug": "alfa", "company": "Альфа ТОО",
                           "discrepancy": "701.00 в реестре, отменена", "source": "календарь §0"}]
    assert client.get("/api/ops/reports/discrepancies", headers=emp).status_code == 404


def test_exports(env):
    client, owner, emp, _ = env
    client.post("/api/ops/reports/plan/load", headers=owner)
    r = client.get("/api/ops/reports/export/registry", headers=owner)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert sorted(wb.sheetnames) == ["200.00", "300.00", "700.00"]  # 910.00 совпал с историей — не в плане
    ws = wb["300.00"]
    assert [c.value for c in ws[1]] == ["№", "Наименование компании", "БИН", "Режим", "НДС", "Форма", "4 кв. 2026"]
    assert ws["G2"].value.startswith("уточнить: НДС не подтверждён")
    r = client.get("/api/ops/reports/export/flat?status=clarify", headers=owner)
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.max_row == 3 and ws["A1"].value == "Компания"
    assert {ws.cell(row=i, column=5).value for i in (2, 3)} == {"300.00", "700.00"}
    assert client.get("/api/ops/reports/export/flat", headers=emp).status_code == 404
    assert client.get("/api/ops/reports/export/other", headers=owner).status_code == 404


def test_read_plan_csv_requires_columns():
    with pytest.raises(plan_mod.PlanError):
        read_plan_csv("company_slug,form\nx,y\n")
    assert len(read_plan_csv("﻿" + CSV)) == 5
