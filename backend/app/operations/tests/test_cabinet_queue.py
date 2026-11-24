"""Очередь на вход в кабинет (ops_cabinet_queue) и блок cabinet: в карточке — для knp-watch (24.11.2026)."""
import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.database import Base, get_db
import app.users.models  # noqa: F401
from app.users.models import User
from app.operations import access
from app.operations import cabinet_queue as cq
from app.operations import cli
from app.operations.access import OpsGateMiddleware
from app.operations.models import OpsCabinetQueue, OpsCompany, UserRoleAssignment
from app.operations.router import ext_router, router

CABINET = {
    "checked_at": "2026-11-24", "status": "пройдена",
    "statement": {"ordered_at": "2026-11-24", "from": "2026-01-01", "ready": True},
    "saldo": {"date": "2026-11-24", "fresh": True, "pages": "2 из 2", "debt_total": 1500, "overpaid_total": 0,
              "rows": [{"kbk": "101202", "ogd": "600901", "tax": -1500, "penalty": 0, "fine": 0}]},
    "notices": {"from": "2026-10-01", "items": []},
    "reports_checked_through": "2026-11-24", "reports": [],
}


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    users = {
        "owner": User(email="owner@t.kz", hashed_password="x", full_name="В", role="admin", is_active=True),
        "staff": User(email="staff@t.kz", hashed_password="x", full_name="С", role="employee", is_active=True),
        "client": User(email="client@t.kz", hashed_password="x", full_name="П", role="client", is_active=True),
    }
    db.add_all(users.values())
    db.commit()
    db.add(UserRoleAssignment(user_id=users["owner"].id, role="admin"))
    db.add(UserRoleAssignment(user_id=users["staff"].id, role="staff"))
    comps = {
        "alfa": OpsCompany(slug="alfa", name="Альфа ТОО", bin="111111111111", active=True,
                           card_json={"id": "alfa", "cabinet": CABINET}),
        "beta": OpsCompany(slug="beta", name="Бета ТОО", bin="222222222222", active=True, card_json={"id": "beta"}),
        "nokey": OpsCompany(slug="nokey", name="Без ключа ИП", active=True,
                            card_json={"id": "nokey", "systems": {"esign": "none"}}),
        "old": OpsCompany(slug="old", name="Архив ТОО", active=False, card_json={"id": "old"}),
    }
    db.add_all(comps.values())
    db.commit()

    app = FastAPI()
    app.add_middleware(OpsGateMiddleware, session_factory=Session)
    app.include_router(ext_router)
    app.include_router(router)

    def _get_db():
        x = Session()
        try:
            yield x
        finally:
            x.close()

    app.dependency_overrides[get_db] = _get_db
    monkeypatch.setattr(access, "SessionLocal", Session)
    client = TestClient(app, raise_server_exceptions=False)
    hdr = {k: {"Authorization": "Bearer " + create_access_token({"sub": u.email})} for k, u in users.items()}
    hdr["anon"] = {}
    ids = {c.slug: c.id for c in comps.values()}
    yield client, hdr, ids, db, Session
    db.close()


def test_card_shows_cabinet_block_to_admin_and_staff(env):
    client, hdr, ids, *_ = env
    for who in ("owner", "staff"):
        d = client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr[who]).json()
        assert d["cabinet"]["saldo"]["debt_total"] == 1500 and d["cabinet"]["checked_at"] == "2026-11-24"
    assert client.get(f"/api/ops/companies/{ids['beta']}", headers=hdr["owner"]).json()["cabinet"] is None
    # очередь видна только admin
    assert "cabinet_queue" in client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["owner"]).json()
    assert "cabinet_queue" not in client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["staff"]).json()


def test_queue_add_list_done_admin_only(env):
    client, hdr, ids, db, _ = env
    url = f"/api/ops/companies/{ids['beta']}/cabinet-queue"
    for who in ("staff", "client", "anon"):
        assert client.post(url, headers=hdr[who], json={}).status_code == 404
        assert client.get("/api/ops/cabinet-queue", headers=hdr[who]).status_code == 404
    r = client.post(url, headers=hdr["owner"], json={"note": "перед 300.00"})
    assert r.status_code == 200 and r.json()["created"] is True
    # повторно — та же запись, вторая не создаётся
    r2 = client.post(url, headers=hdr["owner"], json={})
    assert r2.json()["created"] is False and r2.json()["entry"]["id"] == r.json()["entry"]["id"]
    # архивную — нельзя
    assert client.post(f"/api/ops/companies/{ids['old']}/cabinet-queue", headers=hdr["owner"], json={}).status_code == 400
    items = client.get("/api/ops/cabinet-queue", headers=hdr["owner"]).json()["items"]
    assert [(i["slug"], i["reason"], i["requested_by"], i["note"]) for i in items] == [("beta", "manual", "owner@t.kz", "перед 300.00")]
    card = client.get(f"/api/ops/companies/{ids['beta']}", headers=hdr["owner"]).json()
    assert card["cabinet_queue"]["id"] == items[0]["id"]
    eid = items[0]["id"]
    assert client.post(f"/api/ops/cabinet-queue/{eid}/done", headers=hdr["staff"], json={}).status_code == 404
    assert client.post(f"/api/ops/cabinet-queue/{eid}/done", headers=hdr["owner"], json={}).status_code == 200
    assert client.post(f"/api/ops/cabinet-queue/{eid}/done", headers=hdr["owner"], json={}).status_code == 409
    assert client.get("/api/ops/cabinet-queue", headers=hdr["owner"]).json()["items"] == []
    e = db.query(OpsCabinetQueue).get(eid)
    db.refresh(e)
    assert e.done_by == "owner@t.kz" and e.result == "снято вручную"  # история не удаляется


def test_schedule_candidates_skip_fresh_nokey_archive_queued(env):
    _, _, ids, db, _ = env
    today = dt.date(2026, 11, 30)
    assert [c.slug for c in cq.schedule_candidates(db, 14, today)] == ["beta"]  # alfa проверена 6 дней назад
    assert [c.slug for c in cq.schedule_candidates(db, 14, dt.date(2026, 12, 8))] == ["alfa", "beta"]
    cq.enqueue(db, db.query(OpsCompany).filter_by(slug="beta").one(), "manual")
    assert cq.schedule_candidates(db, 14, today) == []


def test_cli_add_list_done(env, monkeypatch, capsys):
    _, _, _, db, Session = env
    monkeypatch.setattr(cli, "SessionLocal", Session)
    monkeypatch.setattr(cli.Base.metadata, "create_all", lambda **k: None)
    monkeypatch.setattr(cli, "ensure_ops_schema", lambda e: [])
    assert cli.main(["cabinet-queue", "add", "--slug", "alfa", "--by", "knp-watch"]) == 0
    assert cli.main(["cabinet-queue", "list"]) == 0
    out = capsys.readouterr().out
    assert "alfa | Альфа ТОО | 111111111111 | вручную" in out and "последняя проверка 2026-11-24" in out
    assert cli.main(["cabinet-queue", "done", "--slug", "alfa", "--result", "пройдена"]) == 0
    assert cli.main(["cabinet-queue", "done", "--slug", "alfa"]) == 1  # снимать нечего
    assert cli.main(["cabinet-queue", "schedule"]) == 0
    assert "Поставить — с --apply" in capsys.readouterr().out  # без --apply ничего не ставит
    assert db.query(OpsCabinetQueue).filter(OpsCabinetQueue.done_at.is_(None)).count() == 0
