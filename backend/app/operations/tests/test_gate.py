"""Граница безопасности модуля — раздел 1.1 ТЗ «Закрыто по умолчанию».

Гоняется настоящий OpsGateMiddleware с настоящими JWT, без подмены get_current_user.
"""
import logging

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
from app.operations.access import ROUTE_PERMISSIONS, OpsGateMiddleware
from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany, UserRoleAssignment
from app.operations.router import ext_router, router

SECRET_NAME = "ТОО «Секретная Компания»"
SECRET_BIN = "123456789012"


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    owner = User(email="owner@t.kz", hashed_password="x", full_name="Владелец", role="admin", is_active=True)
    other_admin = User(email="admin2@t.kz", hashed_password="x", full_name="Другой админ", role="admin", is_active=True)
    employee = User(email="emp@t.kz", hashed_password="x", full_name="Сотрудник", role="employee", is_active=True)
    viewer = User(email="viewer@t.kz", hashed_password="x", full_name="Зритель", role="employee", is_active=True)
    db.add_all([owner, other_admin, employee, viewer])
    db.commit()
    db.add(OpsCompany(slug="secret", name=SECRET_NAME, bin=SECRET_BIN, card_json={"name": SECRET_NAME}, active=True))
    db.add(UserRoleAssignment(user_id=owner.id, role="admin"))
    db.add(UserRoleAssignment(user_id=viewer.id, role="viewer"))
    db.commit()

    app = FastAPI()
    app.add_middleware(OpsGateMiddleware, session_factory=Session)
    app.include_router(ext_router)
    app.include_router(router)

    @app.get("/api/ops/unlisted", name="ops_unlisted_probe")
    def _unlisted():
        return {"leak": SECRET_NAME}

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

    yield client, hdr, {"owner": owner, "other_admin": other_admin, "employee": employee, "viewer": viewer}, app
    db.close()


OPS_GETS = ["/api/ops/companies", "/api/ops/admins", "/api/ops/companies/1", "/api/ops/status", "/api/ops/ui/bundle.js", "/api/ops/nope", "/api/ops"]


@pytest.mark.parametrize("who", [None, "employee", "other_admin", "viewer"])
def test_non_admin_gets_404_everywhere(env, who):
    client, hdr, users, _ = env
    headers = hdr(users[who]) if who else {}
    for path in OPS_GETS:
        r = client.get(path, headers=headers)
        assert r.status_code == 404, (who, path)
        assert SECRET_NAME not in r.text and SECRET_BIN not in r.text
    for path in ["/api/ops/companies/sync", "/api/ops/reports/import/commit"]:
        assert client.post(path, headers=headers, json={"rows": []}).status_code == 404


def test_users_role_admin_alone_is_not_enough(env):
    """users.role == 'admin' без строки в user_roles — не admin модуля."""
    client, hdr, users, _ = env
    assert client.get("/users/me/extensions", headers=hdr(users["other_admin"])).json() == []


def test_owner_sees_registry(env):
    client, hdr, users, _ = env
    r = client.get("/api/ops/companies", headers=hdr(users["owner"]))
    assert r.status_code == 200
    assert r.json()["items"][0]["bin"] == SECRET_BIN
    adm = client.get("/api/ops/admins", headers=hdr(users["owner"])).json()
    assert [a["email"] for a in adm["items"]] == ["owner@t.kz"]
    ext = client.get("/users/me/extensions", headers=hdr(users["owner"])).json()
    assert [e["key"] for e in ext] == ["ops", "ops-service"]


def test_extensions_empty_for_non_admin(env):
    client, hdr, users, _ = env
    for who in ("employee", "viewer"):
        assert client.get("/users/me/extensions", headers=hdr(users[who])).json() == []


def test_default_deny_route_without_permission_entry(env):
    """Маршрут, не внесённый в ROUTE_PERMISSIONS, недоступен даже admin."""
    client, hdr, users, _ = env
    r = client.get("/api/ops/unlisted", headers=hdr(users["owner"]))
    assert r.status_code == 404 and SECRET_NAME not in r.text


def test_every_real_route_is_explicitly_listed(env):
    _, _, _, app = env
    names = {r.name for r in router.routes}
    assert names <= set(ROUTE_PERMISSIONS), names - set(ROUTE_PERMISSIONS)


def test_flag_off_viewer_role_gives_nothing_flag_on_still_nothing_without_whitelist(env, monkeypatch):
    client, hdr, users, _ = env
    assert client.get("/api/ops/companies", headers=hdr(users["viewer"])).status_code == 404
    monkeypatch.setattr(get_ops_settings(), "ops_registry_visible_to_non_admin", True)
    # Флаг включён, но ROUTE_PERMISSIONS сейчас открывают маршруты только admin.
    assert client.get("/api/ops/companies", headers=hdr(users["viewer"])).status_code == 404


def test_filter_fields_viewer_whitelist_is_empty():
    assert access.filter_fields({"name": "x", "bin": "1"}, {"viewer"}) == {}
    assert access.filter_fields({"name": "x"}, {"admin"}) == {"name": "x"}


def test_errors_do_not_leak_company_data(env, caplog):
    client, hdr, users, app = env

    @app.get("/api/ops/boom", name="ops_boom_probe")
    def _boom():
        raise ValueError(f"{SECRET_NAME} {SECRET_BIN} https://1c.example/base")

    ROUTE_PERMISSIONS["ops_boom_probe"] = {"admin"}
    try:
        with caplog.at_level(logging.DEBUG):
            r = client.get("/api/ops/boom", headers=hdr(users["owner"]))
        assert r.status_code == 500
        for leak in (SECRET_NAME, SECRET_BIN, "1c.example"):
            assert leak not in r.text
            assert leak not in caplog.text
    finally:
        ROUTE_PERMISSIONS.pop("ops_boom_probe", None)
