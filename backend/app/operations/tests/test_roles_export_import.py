"""Итерация 3: роль staff, экспорт xlsx, импорт форм. Три роли — admin, staff, подписчик/без входа."""
import io
import subprocess

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.database import Base, get_db
import app.users.models  # noqa: F401
from app.users.models import User
from app.operations import access, cli
from app.operations.access import OpsGateMiddleware
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, UserRoleAssignment
from app.operations.router import ext_router, router
from app.operations.sync import sync_companies

HIDDEN_NAME = "Тайная ТОО"
CARDS = {
    "alfa": """id: alfa
name: "Альфа ТОО"
bin: "111111111111"
tax:
  regime: general
  vat_payer: true
  forms:
    - form: '300.00'
      source: import_xlsx
    - form: '101.04'
      period: 2026-Q4
      basis: "Foo Ltd → услуги → $1 000 → п/п №1"
obligation_flags: []
active: true
inactive_since: null
kgd:
  vat_date: '2025-03-05'
""",
    "beta": """id: beta
name: "Бета ИП"
bin: "222222222222"
tax:
  regime: simplified
  vat_payer: false
  forms: []   # формы
obligation_flags: []
active: true
inactive_since: null
""",
    "secret": f"""id: secret
name: "{HIDDEN_NAME}"
bin: "333333333333"
tax:
  regime: general
  vat_payer: false
  forms:
    - form: '200.00'
obligation_flags: []
active: true
inactive_since: null
hidden: true
""",
}


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    # репозиторий allkey-ops: удалённый (bare) + клон на ветке prod-decisions
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "arty"
    for slug, text in CARDS.items():
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
    r = sync_companies(db, skip_validator=True)
    assert r.ok and r.total == 3

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
    yield client, hdr, ids, work, remote, Session
    db.close()


STAFF_OPEN_GET = ["/api/ops/companies", "/api/ops/status", "/api/ops/me", "/api/ops/ui/bundle.js"]
ADMIN_ONLY_GET = ["/api/ops/companies/1", "/api/ops/admins", "/api/ops/kgd/check?bin=111111111111"]
ADMIN_ONLY_POST = ["/api/ops/companies/sync", "/api/ops/companies/1/hidden", "/api/ops/reports/import/commit",
                   "/api/ops/companies/forms-import/apply", "/api/ops/companies/1/obligations"]


def test_admin_everything(env):
    client, hdr, ids, *_ = env
    assert client.get("/api/ops/me", headers=hdr["owner"]).json() == {"role": "admin"}
    items = client.get("/api/ops/companies", headers=hdr["owner"]).json()["items"]
    assert len(items) == 3 and any(i["hidden"] for i in items)
    assert client.get(f"/api/ops/companies/{ids['alfa']}", headers=hdr["owner"]).status_code == 200
    ext = client.get("/users/me/extensions", headers=hdr["owner"]).json()
    assert [e["key"] for e in ext] == ["ops", "ops-service"]


def test_staff_sees_list_not_admin_parts(env):
    client, hdr, ids, *_ = env
    h = hdr["staff"]
    for p in STAFF_OPEN_GET:
        assert client.get(p, headers=h).status_code == 200, p
    assert client.get("/api/ops/me", headers=h).json() == {"role": "staff"}
    items = client.get("/api/ops/companies", headers=h).json()["items"]
    assert sorted(i["slug"] for i in items) == ["alfa", "beta"]
    alfa = next(i for i in items if i["slug"] == "alfa")
    assert alfa["forms"] == ["300.00", "101.04"] and alfa["vat_date"] == "2025-03-05"
    assert "hidden" not in alfa and "suspected_count" not in alfa
    st = client.get("/api/ops/status", headers=h).json()
    assert st["total"] == 2 and "hidden" not in st
    for p in ADMIN_ONLY_GET + [f"/api/ops/companies/{ids['alfa']}"]:
        assert client.get(p, headers=h).status_code == 404, p
    for p in ADMIN_ONLY_POST:
        assert client.post(p, headers=h, json={"hidden": True, "rows": [], "changes": []}).status_code == 404, p
    r = client.post("/api/ops/companies/forms-import/preview", headers=h, files={"file": ("x.xlsx", b"x")})
    assert r.status_code == 404
    # в меню — только «Компании», без «Служебного»
    ext = client.get("/users/me/extensions", headers=h).json()
    assert [(e["key"], e.get("settings")) for e in ext] == [("ops", None)]


@pytest.mark.parametrize("who", ["client", "anon"])
def test_subscriber_and_anon_get_404(env, who):
    client, hdr, ids, *_ = env
    h = hdr[who]
    for p in STAFF_OPEN_GET + ADMIN_ONLY_GET:
        r = client.get(p, headers=h)
        assert r.status_code == 404, (who, p)
        assert HIDDEN_NAME not in r.text
    for p in ADMIN_ONLY_POST + ["/api/ops/companies/export"]:
        assert client.post(p, headers=h, json={"ids": list(ids.values())}).status_code == 404, (who, p)
    if who == "client":
        assert client.get("/users/me/extensions", headers=h).json() == []


def _xlsx(resp):
    ws = load_workbook(io.BytesIO(resp.content)).active
    return [[c.value for c in r] for r in ws.iter_rows()]


def test_export_columns_and_hidden(env):
    client, hdr, ids, *_ = env
    all_ids = [ids["alfa"], ids["secret"], ids["beta"]]
    r = client.post("/api/ops/companies/export", headers=hdr["owner"], json={"ids": all_ids})
    rows = _xlsx(r)
    assert rows[0] == ["Название", "БИН", "Режим", "НДС", "НДС с", "Формы", "300.00", "200.00", "101.04", "220.00",
                       "100.00", "910.00", "700.00", "Папка на Диске"]
    assert [x[0] for x in rows[1:]] == ["Альфа ТОО", HIDDEN_NAME, "Бета ИП"]  # порядок экрана, admin видит скрытую
    alfa = rows[1]
    assert alfa[1:6] == ["111111111111", "ОУР", "да", "05.03.2025", "300.00, 101.04"]
    assert alfa[6:13] == ["да", None, "да", None, None, None, None]
    # сотрудник: те же id, скрытой нет
    rows = _xlsx(client.post("/api/ops/companies/export", headers=hdr["staff"], json={"ids": all_ids}))
    assert [x[0] for x in rows[1:]] == ["Альфа ТОО", "Бета ИП"]
    assert HIDDEN_NAME not in str(rows)


def _import_file(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Название", "БИН", "Режим", "НДС", "НДС с", "Формы", "300.00", "200.00", "101.04", "220.00", "100.00",
               "910.00", "700.00", "Папка на Диске"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_forms_import_preview_apply(env):
    client, hdr, ids, work, remote, Session = env
    content = _import_file([
        # Альфа: +200.00, 300.00 «нет» → убрать, 101.04 «нет» — заблокировано (обязательство), НДС «нет» ≠ карточка
        ["Альфа ТОО", "111111111111", "ОУР", "нет", "", "", "нет", "да", "нет", "", "", "", "", ""],
        # Бета: +910.00, режим «ОУР» ≠ упрощёнка — расхождение, режим не меняется
        ["Бета ИП", "222222222222", "ОУР", "нет", "", "", "", "", "", "", "", "да", "", ""],
        ["Неизвестная ТОО", "999999999999", "", "", "", "", "да", "", "", "", "", "", "", ""],
        ["Кривая ТОО", "111111111112", "", "", "", "", "может", "", "", "", "", "", "", ""],
    ])
    r = client.post("/api/ops/companies/forms-import/preview", headers=hdr["owner"],
                    files={"file": ("Реестр.xlsx", content)})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["companies_in_file"] == 4 and p["matched"] == 2
    ch = {c["slug"]: (c["add"], c["remove"]) for c in p["changes"]}
    assert ch == {"alfa": (["200.00"], ["300.00"]), "beta": (["910.00"], [])}
    assert [b["form"] for b in p["blocked"]] == ["101.04"]
    assert sorted((d["company"], d["field"]) for d in p["discrepancies"]) == [("Альфа ТОО", "НДС"), ("Бета ИП", "режим")]
    assert {u["bin"] for u in p["unmatched"]} == {"999999999999", "111111111112"}
    assert any("может" in w for w in p["warnings"])
    # предпросмотр ничего не писал
    assert git(work, "status", "--porcelain").stdout.strip() == ""

    body = {"file_name": p["file_name"], "changes": [{"company_id": c["company_id"], "add": c["add"], "remove": c["remove"]}
                                                       for c in p["changes"]],
            "companies_in_file": p["companies_in_file"], "unmatched": len(p["unmatched"]),
            "discrepancies": len(p["discrepancies"]), "blocked": len(p["blocked"])}
    r = client.post("/api/ops/companies/forms-import/apply", headers=hdr["owner"], json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["companies_changed"], res["forms_added"], res["forms_removed"]) == (2, 2, 1)

    alfa = yaml.safe_load((work / "clients" / "alfa" / "client.yaml").read_text(encoding="utf-8"))
    forms = alfa["tax"]["forms"]
    assert [f["form"] for f in forms] == ["101.04", "200.00"]
    assert forms[1]["source"] == "import_xlsx" and forms[1]["date"]
    assert alfa["tax"]["vat_payer"] is True and alfa["tax"]["regime"] == "general"  # режим/НДС не тронуты
    beta = yaml.safe_load((work / "clients" / "beta" / "client.yaml").read_text(encoding="utf-8"))
    assert beta["tax"]["regime"] == "simplified" and [f["form"] for f in beta["tax"]["forms"]] == ["910.00"]

    # один коммит в prod-decisions на удалённом, вместе с журналом
    log = git(remote, "log", "--format=%an|%s", "prod-decisions").stdout.strip().splitlines()
    assert log[0].startswith("Allkey (система)|forms-import: 2 карточ(ек), +2 / -1 форм — файл «Реестр.xlsx»")
    files = git(remote, "show", "--name-only", "--format=", "prod-decisions").stdout.split()
    assert sorted(files) == ["clients/alfa/client.yaml", "clients/beta/client.yaml", "reports/forms-import-log.csv"]
    journal = (work / "reports" / "forms-import-log.csv").read_text(encoding="utf-8")
    assert "Реестр.xlsx" in journal and "owner@t.kz" in journal
    # панель пересинхронизирована
    items = client.get("/api/ops/companies", headers=hdr["owner"]).json()["items"]
    assert next(i for i in items if i["slug"] == "beta")["forms"] == ["910.00"]
    # повтор того же применения — ничего не меняет
    r = client.post("/api/ops/companies/forms-import/apply", headers=hdr["owner"], json=body)
    assert r.json()["companies_changed"] == 0


def test_cli_grant_revoke_staff(env, monkeypatch, capsys):
    client, hdr, ids, work, remote, Session = env
    monkeypatch.setattr(cli, "SessionLocal", Session)
    monkeypatch.setattr(cli, "engine", Session.kw["bind"])
    assert cli.main(["grant-staff", "--email", "client@t.kz"]) == 0
    assert client.get("/api/ops/companies", headers=hdr["client"]).status_code == 200
    assert cli.main(["revoke-staff", "--email", "client@t.kz"]) == 0
    assert client.get("/api/ops/companies", headers=hdr["client"]).status_code == 404
    assert cli.main(["grant-staff", "--email", "nobody@t.kz"]) == 1
