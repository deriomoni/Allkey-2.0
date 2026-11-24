"""Итерация 4: карточка для сотрудника — правка 1С, заметки, флаг «подозрение»; всё коммитом в prod-decisions."""
import subprocess

import pytest
import yaml
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
from app.operations.access import OpsGateMiddleware
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, UserRoleAssignment
from app.operations.router import ext_router, router
from app.operations.sync import sync_companies

CARD = """# карточка
id: alfa
name: "Альфа ТОО"
bin: "111111111111"
tax:
  regime: general
  vat_payer: true
  forms: []   # формы

# --- Обязательства ---
obligation_flags: []

systems:
  onec:
    kind: cloud                       # cloud | local | none
    note: ""                          # заметка
    url: "https://old.example/base"   # старый адрес
    login: agent
    run_on: server
    closed_through: null
  # esign: none
  drive:
    root_folder_id: "ROOT1234567890abcdefXYZ"
    agent_folder_id: "AGENT1234567890abcdefXYZ"
    profile_folder_id: "PROF1234567890abcdefXYZ"
    folder_name: "Альфа ТОО"
active: true
inactive_since: null
"""
SECRET = CARD.replace("id: alfa", "id: secret").replace("Альфа ТОО", "Тайная ТОО").replace(
    "111111111111", "333333333333") + "hidden: true\n"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "arty"
    for slug, text in (("alfa", CARD), ("secret", SECRET)):
        (work / "clients" / slug).mkdir(parents=True)
        (work / "clients" / slug / "client.yaml").write_text(text, encoding="utf-8", newline="\n")
    (work / "scripts").mkdir()
    (work / "scripts" / "validate_cards.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    git(work, "init", "-q", "-b", "main")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-q", "-b", "prod-decisions")
    s = get_ops_settings()
    monkeypatch.setattr(s, "arty_ops_path", str(work))
    monkeypatch.setattr(s, "ops_repo_push", True)
    monkeypatch.setattr(s, "ops_repo_branch", "prod-decisions")

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
    db.commit()
    assert sync_companies(db, skip_validator=True).ok

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
    ids = {c.slug: c.id for c in db.query(OpsCompany).all()}
    yield client, hdr, ids, work, remote
    db.close()


def card(work, slug="alfa"):
    return yaml.safe_load((work / "clients" / slug / "client.yaml").read_text(encoding="utf-8"))


def remote_log(remote):
    return git(remote, "log", "--format=%an|%s", "prod-decisions").stdout.strip().splitlines()


def test_staff_opens_card_without_agent_and_hidden(env):
    client, hdr, ids, *_ = env
    r = client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["staff"])
    assert r.status_code == 200
    d = r.json()
    assert d["onec"]["url"] == "https://old.example/base" and d["onec"]["login"] == "agent"
    assert "agent_url" not in d["drive"] and "AGENT1234" not in r.text
    assert "hidden" not in d["card"] and "hidden" not in d
    assert d["profile"] is None and d["profile_url"].endswith("PROF1234567890abcdefXYZ")
    # admin видит _agent
    a = client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["owner"]).json()
    assert a["drive"]["agent_url"]
    # скрытая — 404 сотруднику, подписчику и без входа — 404 на карточку
    assert client.get(f"/api/ops/companies/{ids['secret']}", headers=hdr["staff"]).status_code == 404
    for who in ("client", "anon"):
        assert client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr[who]).status_code == 404


def test_staff_edits_onec_with_reason(env):
    client, hdr, ids, work, remote = env
    url = f"/api/ops/companies/{ids['alfa']}/onec"
    assert client.post(url, headers=hdr["staff"], json={"url": "https://new.example/b"}).status_code == 422  # нет reason
    assert client.post(url, headers=hdr["staff"], json={"url": "https://new.example/b", "reason": ""}).status_code == 400
    assert client.post(url, headers=hdr["staff"], json={"url": "ftp://x", "reason": "переезд"}).status_code == 400
    assert client.post(url, headers=hdr["staff"], json={"kind": "weird", "reason": "переезд"}).status_code == 400
    r = client.post(url, headers=hdr["staff"],
                    json={"url": "https://new.example/b", "note": "переехали на host1c", "reason": "база переехала"})
    assert r.status_code == 200, r.text
    c = card(work)
    onec = c["systems"]["onec"]
    assert onec["url"] == "https://new.example/b" and onec["note"] == "переехали на host1c"
    assert onec["login"] == "agent" and onec["run_on"] == "server" and onec["kind"] == "cloud"
    assert onec["edited"]["by"] == "staff@t.kz" and onec["edited"]["reason"] == "база переехала"
    text = (work / "clients" / "alfa" / "client.yaml").read_text(encoding="utf-8")
    assert "# карточка" in text and "# --- Обязательства ---" in text and "  # esign: none" in text
    assert "изменил staff@t.kz" in text
    log = remote_log(remote)
    assert log[0].startswith("Allkey (система)|onec: alfa — адрес/тип/заметка базы 1С изменены (staff@t.kz): база переехала")
    # панель видит новое
    d = client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["staff"]).json()
    assert d["onec"]["url"] == "https://new.example/b"
    # подписчик — 404
    assert client.post(url, headers=hdr["client"], json={"url": "https://x.y/z", "reason": "abc"}).status_code == 404


def test_staff_notes_general_and_form(env):
    client, hdr, ids, work, remote = env
    url = f"/api/ops/companies/{ids['alfa']}/notes"
    assert client.post(url, headers=hdr["staff"], json={"text": " "}).status_code == 400
    assert client.post(url, headers=hdr["staff"], json={"text": "Директор сменился в ноябре"}).status_code == 200
    assert client.post(url, headers=hdr["staff"],
                       json={"text": "Сдали с опозданием", "form": "300.00", "period": "2026-Q3"}).status_code == 200
    notes = card(work)["staff_notes"]
    assert [(n["author"], n.get("form"), n["text"]) for n in notes] == [
        ("staff@t.kz", None, "Директор сменился в ноябре"), ("staff@t.kz", "300.00", "Сдали с опозданием")]
    assert notes[1]["period"] == "2026-Q3" and notes[0]["at"]
    text = (work / "clients" / "alfa" / "client.yaml").read_text(encoding="utf-8")
    assert text.index("staff_notes:") < text.index("# --- Обязательства ---")
    assert remote_log(remote)[0].startswith("Allkey (система)|notes: alfa — заметка к 300.00 2026-Q3 (staff@t.kz)")
    d = client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["staff"]).json()
    assert len(d["staff_notes"]) == 2


def test_staff_raises_flag_only_allowed_forms_admin_decides(env):
    client, hdr, ids, work, remote = env
    url = f"/api/ops/companies/{ids['alfa']}/obligations"
    tr = ["Foo Ltd → консультации → $4 200 → п/п №118 от 14.11.2026"]
    r = client.post(url, headers=hdr["staff"], json={"form": "300.00", "period": "2026-Q4", "trigger": tr})
    assert r.status_code == 400 and "только по формам" in r.json()["detail"]
    assert client.post(url, headers=hdr["staff"], json={"form": "328.00", "period": "2026-11", "trigger": []}).status_code == 400
    for form, period in (("101.04", "2026-Q4"), ("328.00", "2026-11"), ("700.00", "2026"),
                         ("отчёт участника Астана Хаб", "2026-Q4")):
        r = client.post(url, headers=hdr["staff"], json={"form": form, "period": period, "trigger": tr})
        assert r.status_code == 200, (form, r.text)
    flags = card(work)["obligation_flags"]
    assert [(f["form"], f["status"], f["source"], f["raised_by"]) for f in flags] == [
        ("101.04", "suspected", "employee", "staff@t.kz"), ("328.00", "suspected", "employee", "staff@t.kz"),
        ("700.00", "suspected", "employee", "staff@t.kz"),
        ("отчёт участника Астана Хаб", "suspected", "employee", "staff@t.kz")]
    assert remote_log(remote)[0].startswith("Allkey (система)|obligations: alfa — подозрение отчёт участника Астана Хаб")
    assert "(сотрудник staff@t.kz)" in remote_log(remote)[0]
    # подтвердить/снять — только admin
    body = {"form": "101.04", "period": "2026-Q4"}
    assert client.post(f"{url}/0/confirm", headers=hdr["staff"], json=body).status_code == 404
    assert client.post(f"{url}/0/dismiss", headers=hdr["staff"], json={**body, "reason": "нет"}).status_code == 404
    assert client.post(f"{url}/0/confirm", headers=hdr["owner"], json=body).status_code == 200
    assert card(work)["obligation_flags"][0]["status"] == "confirmed"
    # admin может любую форму
    assert client.post(url, headers=hdr["owner"], json={"form": "300.00", "period": "2026-Q4", "trigger": tr}).status_code == 200


def test_staff_cannot_touch_hidden_company(env):
    client, hdr, ids, *_ = env
    sid = ids["secret"]
    assert client.post(f"/api/ops/companies/{sid}/onec", headers=hdr["staff"],
                       json={"url": "https://x.y/z", "reason": "abc"}).status_code == 404
    assert client.post(f"/api/ops/companies/{sid}/notes", headers=hdr["staff"], json={"text": "abc"}).status_code == 404
    assert client.post(f"/api/ops/companies/{sid}/obligations", headers=hdr["staff"],
                       json={"form": "101.04", "period": "2026-Q4", "trigger": ["a → b → c → d"]}).status_code == 404
