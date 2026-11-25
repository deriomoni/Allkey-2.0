"""ТЗ 1.1 п. 9 — скрытые компании: видит только admin; для остальных ролей их нет в API."""
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
from app.operations.access import OpsGateMiddleware, route_open_for
from app.operations.card_edit import set_hidden_text
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, OpsObligationFlag, UserRoleAssignment
from app.operations.obligations import ObligationError
from app.operations.router import ext_router, router
from app.operations.sync import card_to_columns

HIDDEN_NAME = "ТОО «Закрытая»"
HIDDEN_BIN = "999999999999"

CARD = """# карточка
id: secret
name: "Закрытая ТОО"  # имя
bin: "999999999999"
tax:
  regime: general
active: true                          # активна
inactive_reason: null
inactive_since: null                  # дата
# комментарий после
since: 2026-01-01
"""


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    owner = User(email="owner@t.kz", hashed_password="x", full_name="Владелец", role="admin", is_active=True)
    viewer = User(email="viewer@t.kz", hashed_password="x", full_name="Зритель", role="employee", is_active=True)
    db.add_all([owner, viewer])
    db.commit()
    open_c = OpsCompany(slug="open", name="Открытая ТОО", bin="111111111111", card_json={}, active=True)
    arch = OpsCompany(slug="old", name="Архивная ТОО", bin="222222222222", card_json={}, active=False)
    hid = OpsCompany(slug="secret", name=HIDDEN_NAME, bin=HIDDEN_BIN, card_json={}, active=True, hidden=True)
    hid_arch = OpsCompany(slug="secret-old", name=HIDDEN_NAME + " 2", bin="333333333333", card_json={},
                          active=False, hidden=True)
    db.add_all([open_c, arch, hid, hid_arch])
    db.commit()
    db.add(OpsObligationFlag(company_id=hid.id, idx=0, form="101.04", status="suspected"))
    db.add(UserRoleAssignment(user_id=owner.id, role="admin"))
    db.add(UserRoleAssignment(user_id=viewer.id, role="staff"))
    db.commit()

    # Репозиторий с карточкой скрытой компании — для переключателя.
    repo = tmp_path / "arty"
    (repo / "clients" / "secret").mkdir(parents=True)
    (repo / "clients" / "secret" / "client.yaml").write_text(CARD, encoding="utf-8", newline="\n")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "validate_cards.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(repo))
    monkeypatch.setattr(get_ops_settings(), "ops_repo_push", False)

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

    ids = {"open": open_c.id, "secret": hid.id, "secret_old": hid_arch.id}
    yield client, hdr(owner), hdr(viewer), ids, repo, Session
    db.close()


@pytest.fixture
def viewer_opened(env, monkeypatch):
    """Пользователь с ролью staff (сотрудник). Карточку сотруднику не открывают; чтобы проверить
    фильтр скрытых и в карточке, открываем её для staff в этом тесте (обработчик + гейт)."""
    client = env[0]
    from app.auth.dependencies import get_current_user
    from app.operations.access import require_ops_admin
    client.app.dependency_overrides[require_ops_admin] = get_current_user
    perms = dict(access.ROUTE_PERMISSIONS)
    perms["ops_get_company"] = {"admin", "staff"}
    monkeypatch.setattr(access, "ROUTE_PERMISSIONS", perms)


def test_admin_sees_hidden_with_flag(env):
    client, owner, _, ids, _, _ = env
    items = client.get("/api/ops/companies", headers=owner).json()["items"]
    assert {i["slug"]: i["hidden"] for i in items} == {"open": False, "old": False, "secret": True, "secret-old": True}
    assert client.get(f"/api/ops/companies/{ids['secret']}", headers=owner).status_code == 200
    st = client.get("/api/ops/status", headers=owner).json()
    assert (st["total"], st["active"], st["hidden"]) == (4, 2, 2)


def test_viewer_does_not_see_hidden_anywhere(env, viewer_opened):
    client, _, viewer, ids, _, _ = env
    r = client.get("/api/ops/companies", headers=viewer)
    assert r.status_code == 200
    assert sorted(i["slug"] for i in r.json()["items"]) == ["old", "open"]
    assert HIDDEN_NAME not in r.text and HIDDEN_BIN not in r.text
    # карточка — 404, как будто её нет; открытая — 200
    for key in ("secret", "secret_old"):
        r = client.get(f"/api/ops/companies/{ids[key]}", headers=viewer)
        assert r.status_code == 404 and HIDDEN_NAME not in r.text
    assert client.get(f"/api/ops/companies/{ids['open']}", headers=viewer).status_code == 200
    # счётчики — без скрытых и без поля hidden
    st = client.get("/api/ops/status", headers=viewer).json()
    assert (st["total"], st["active"], st["inactive"]) == (2, 1, 1)
    assert "hidden" not in st


def test_gate_closes_routes_without_hidden_filter(env, viewer_opened, monkeypatch):
    """Маршрут, открытый не-admin, но не входящий в HIDDEN_SAFE_ROUTES, — 404 (default deny)."""
    client, owner, viewer, ids, _, _ = env
    perms = dict(access.ROUTE_PERMISSIONS)
    perms["ops_reports_import_preview"] = {"admin", "staff"}
    perms["ops_company_set_hidden"] = {"admin", "staff"}
    monkeypatch.setattr(access, "ROUTE_PERMISSIONS", perms)
    assert not route_open_for("ops_reports_import_preview", {"staff"})
    assert route_open_for("ops_reports_import_preview", {"admin"})
    r = client.post(f"/api/ops/companies/{ids['open']}/hidden", headers=viewer, json={"hidden": True})
    assert r.status_code == 404


def test_every_non_admin_route_is_hidden_safe():
    """Сторож на будущее: всё, что открыто не-admin роли, обязано фильтровать скрытые."""
    # agent — исполнитель владельца по токену (только очередь кабинета, 25.11.2026): видит и скрытые, как admin
    for name, roles in access.ROUTE_PERMISSIONS.items():
        if roles - {"admin", "agent"}:
            assert name in access.HIDDEN_SAFE_ROUTES, name


def test_sync_reads_hidden():
    assert card_to_columns("x", {"active": True})["hidden"] is False
    assert card_to_columns("x", {"active": True, "hidden": True})["hidden"] is True
    assert card_to_columns("x", {"active": True, "hidden": "true"})["hidden"] is False  # только настоящий bool


def test_set_hidden_text_touches_only_hidden():
    t1 = set_hidden_text(CARD, True)
    assert "inactive_since: null                  # дата\nhidden: true\n# комментарий после" in t1
    t2 = set_hidden_text(t1, False)
    assert t2 == t1.replace("hidden: true", "hidden: false")
    with_comment = CARD.replace("since: 2026", "hidden: false   # пояснение\nsince: 2026")
    assert "hidden: true   # пояснение" in set_hidden_text(with_comment, True)
    assert yaml.safe_load(t1) == {**yaml.safe_load(CARD), "hidden": True}


def test_toggle_commits_card_and_resyncs(env):
    client, owner, viewer, ids, repo, Session = env
    # снять «скрытую» с карточки secret (в БД — hidden=true, в карточке поля нет)
    (repo / "clients" / "secret" / "client.yaml").write_text(
        set_hidden_text(CARD, True), encoding="utf-8", newline="\n")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "hidden")
    r = client.post(f"/api/ops/companies/{ids['secret']}/hidden", headers=owner, json={"hidden": False})
    assert r.status_code == 200, r.text
    assert r.json()["hidden"] is False
    card = yaml.safe_load((repo / "clients" / "secret" / "client.yaml").read_text(encoding="utf-8"))
    assert card["hidden"] is False and card["name"] == "Закрытая ТОО"
    log = git(repo, "log", "-1", "--format=%an|%s").stdout.strip()
    assert log.startswith("Allkey (система)|hidden: secret — открыта")
    db = Session()
    assert db.get(OpsCompany, ids["secret"]).hidden is False
    # обратно
    r = client.post(f"/api/ops/companies/{ids['secret']}/hidden", headers=owner, json={"hidden": True})
    assert r.json()["hidden"] is True
    db.expire_all()
    assert db.get(OpsCompany, ids["secret"]).hidden is True
    # не-admin переключать не может (флаг выключен) — 404
    assert client.post(f"/api/ops/companies/{ids['secret']}/hidden", headers=viewer,
                       json={"hidden": False}).status_code == 404


def test_toggle_refuses_dirty_card(env):
    client, owner, _, ids, repo, _ = env
    p = repo / "clients" / "secret" / "client.yaml"
    p.write_text(CARD + "# чужая правка\n", encoding="utf-8", newline="\n")
    r = client.post(f"/api/ops/companies/{ids['secret']}/hidden", headers=owner, json={"hidden": False})
    assert r.status_code == 409
    assert p.read_text(encoding="utf-8").endswith("# чужая правка\n")


def test_set_hidden_text_rejects_broken_yaml():
    with pytest.raises(ObligationError):
        set_hidden_text("a: [unclosed\n", True)
