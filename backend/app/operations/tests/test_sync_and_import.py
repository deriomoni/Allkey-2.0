import io
import textwrap

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.users.models  # noqa: F401
from app.operations import sync as sync_mod
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, OpsCompanyReport
from app.operations.reports_import import cell_status, commit_rows, match_rows, norm, parse_workbook

CARD_A = """
id: alpha
name: ТОО «Альфа Трейд»
aliases: [Alpha, Альфа]
bin: "000000000000"
tax: {regime: general, vat_payer: true}
systems:
  onec: {kind: cloud, url: https://1c.example/a, note: "", closed_through: 2025-12-31}
  drive: {root_folder_id: ROOT1, agent_folder_id: "", folder_name: ТОО Альфа}
responsible: {name: ""}
active: true
"""
CARD_B = """
id: beta
name: ИП Бетов Б.
bin: "111111111111"
tax: {regime: simplified, vat_payer: false}
systems:
  onec: {kind: none, note: нет базы}
  drive: {root_folder_id: "", folder_name: ИП Бетов}
active: false
inactive_reason: клиент ушёл
inactive_since: 2026-10-01
"""


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def make_repo(tmp_path, validator_exit=0):
    for slug, body in (("alpha", CARD_A), ("beta", CARD_B), ("_template", "id: x\n")):
        d = tmp_path / "clients" / slug
        d.mkdir(parents=True)
        (d / "client.yaml").write_text(textwrap.dedent(body), encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_cards.py").write_text(
        "import sys\n"
        + ("print('ОШИБКА  alpha: плохой БИН')\n" if validator_exit else "print('Итого: ошибок 0')\n")
        + f"sys.exit({validator_exit})\n",
        encoding="utf-8",
    )
    return tmp_path


def test_sync_creates_and_is_idempotent(db, tmp_path, monkeypatch):
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(make_repo(tmp_path)))
    r = sync_mod.sync_companies(db)
    assert r.ok and r.created == 2 and r.active == 1 and r.inactive == 1
    a = db.query(OpsCompany).filter_by(slug="alpha").one()
    assert a.aliases == ["Alpha", "Альфа"] and a.drive_root_folder_id == "ROOT1" and a.drive_agent_folder_id is None
    assert a.card_json["systems"]["onec"]["closed_through"] == "2025-12-31"
    b = db.query(OpsCompany).filter_by(slug="beta").one()
    assert b.active is False and b.inactive_reason == "клиент ушёл" and str(b.inactive_since) == "2026-10-01"
    # name пустой → показываем папку на Диске
    assert sync_mod.card_to_columns("x", {"name": "", "systems": {"drive": {"folder_name": "ТОО Икс"}}})["name"] == "ТОО Икс"
    r2 = sync_mod.sync_companies(db)
    assert r2.ok and r2.created == 0 and r2.updated == 0 and r2.unchanged == 2


def test_validator_errors_block_sync(db, tmp_path, monkeypatch):
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(make_repo(tmp_path, validator_exit=1)))
    r = sync_mod.sync_companies(db)
    assert not r.ok and not r.validator_ok
    assert r.validator_errors == ["ОШИБКА  alpha: плохой БИН"]
    assert db.query(OpsCompany).count() == 0


def test_sync_without_repo_path(db, monkeypatch):
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", "")
    r = sync_mod.sync_companies(db)
    assert not r.ok and "ARTY_OPS_PATH" in r.error


def _xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "300.00"
    ws.append(["Отчёты по НДС"])
    ws.append(["№", "Наименование компании", "1 кв 2026", "2 кв 2026", "Примечание"])
    ws.append([1, "Альфа Трейд ТОО", "сдан", "", "x"])
    ws.append([2, "alpha", "принят", "отклонен", None])
    ws.append([3, "Неизвестная", "+", None, None])
    ws2 = wb.create_sheet("910.00")
    ws2.append(["Наименование компании", "2 пг 2025"])
    ws2.append(["ИП Бетов", "не требуется"])
    ws3 = wb.create_sheet("мусор")
    ws3.append(["что-то"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_preview_match_and_commit(db, tmp_path, monkeypatch):
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(make_repo(tmp_path)))
    sync_mod.sync_companies(db)
    parsed = parse_workbook(_xlsx())
    assert [s["form"] for s in parsed["sheets"]] == ["300.00", "910.00"]
    assert parsed["sheets"][0]["periods"] == ["1 кв 2026", "2 кв 2026"]
    assert len(parsed["warnings"]) == 1
    rows = match_rows(db, parsed["rows"])
    by_text = {r["company_text"]: r for r in rows}
    assert by_text["Альфа Трейд ТОО"]["match"]["by"] == "name"
    assert by_text["alpha"]["match"]["by"] == "alias"
    assert by_text["ИП Бетов"]["match"]["by"] == "folder_name"
    assert by_text["Неизвестная"]["match"] is None
    assert [c["status"] for c in by_text["alpha"]["cells"]] == ["accepted", "rejected"]

    alpha_id = by_text["alpha"]["match"]["company_id"]
    res = commit_rows(db, [
        {"company_id": alpha_id, "form": "300.00", "cells": by_text["Альфа Трейд ТОО"]["cells"]},
        {"company_id": alpha_id, "form": "300.00", "cells": by_text["alpha"]["cells"]},
        {"company_id": 99999, "form": "300.00", "cells": []},
    ])
    assert res == {"created": 2, "updated": 1, "skipped": 1}
    reps = {(r.form, r.period): r for r in db.query(OpsCompanyReport).all()}
    assert reps[("300.00", "1 кв 2026")].status == "accepted"
    assert reps[("300.00", "1 кв 2026")].source == "import_xlsx"


def test_norm_and_status():
    assert norm("ТОО «Альфа-Трейд»") == norm("альфа трейд")
    assert cell_status(None) is None and cell_status("  ") is None
    assert cell_status("Сдано 15.05") == "submitted"
    assert cell_status("—") == "not_required"



def test_load_rows_only_adds(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.operations.models import OpsCompany, OpsCompanyReport
    from app.operations.reports_import import load_rows
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    c = OpsCompany(slug="a", name="A", card_json={}, active=True)
    db.add(c)
    db.commit()
    db.add(OpsCompanyReport(company_id=c.id, form="300.00", period="2026-Q3", status="accepted", source="import_xlsx"))
    db.commit()
    rows = [
        {"slug": "a", "form": "300.00", "period": "2026-Q3", "status": "due", "source": "plan"},  # уже есть
        {"slug": "a", "form": "300.00", "period": "2026-Q4", "status": "due", "raw_value": "ожидается", "source": "plan"},
        {"slug": "a", "form": "200.00", "period": "2026-Q4", "status": "clarify", "source": "plan"},
        {"slug": "zz", "form": "300.00", "period": "2026-Q4", "status": "due", "source": "plan"},
        {"slug": "a", "form": "100.00", "period": "2026", "status": "weird", "source": "plan"},
    ]
    assert load_rows(db, rows) == {"created": 2, "skipped_existing": 1, "unknown_company": 1, "invalid": 1}
    old = db.query(OpsCompanyReport).filter_by(period="2026-Q3").one()
    assert (old.status, old.source) == ("accepted", "import_xlsx")
    assert load_rows(db, rows)["created"] == 0
