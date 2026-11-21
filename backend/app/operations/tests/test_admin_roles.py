"""Роль admin модуля: .env, CLI grant/revoke, смена OPS_ADMIN_USER_ID."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.users.models  # noqa: F401
from app.users.models import User
from app.operations.access import ensure_admin_from_env, grant_admin, list_admins, revoke_admin
from app.operations.config import get_ops_settings
from app.operations.models import UserRoleAssignment


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    for i in (1, 2, 3):
        s.add(User(id=i, email=f"u{i}@example.com", hashed_password="x", full_name=f"U{i}", role="admin"))
    s.commit()
    yield s
    s.close()


def admins(db):
    return sorted((r.user_id, r.granted_by) for r in db.query(UserRoleAssignment).filter_by(role="admin").all())


def set_env(monkeypatch, uid):
    monkeypatch.setattr(get_ops_settings(), "ops_admin_user_id", uid)


def test_changing_env_id_revokes_previous_env_admin(db, monkeypatch):
    set_env(monkeypatch, 1)
    ensure_admin_from_env(db)
    assert admins(db) == [(1, "env")]
    set_env(monkeypatch, 2)
    ensure_admin_from_env(db)
    assert admins(db) == [(2, "env")]


def test_explicit_cli_grant_survives_env_change(db, monkeypatch):
    set_env(monkeypatch, 1)
    ensure_admin_from_env(db)
    grant_admin(db, 3, granted_by="cli")
    grant_admin(db, 1, granted_by="cli")  # закрепляет env-роль явно
    set_env(monkeypatch, 2)
    ensure_admin_from_env(db)
    assert admins(db) == [(1, "cli"), (2, "env"), (3, "cli")]


def test_unset_env_revokes_env_admin(db, monkeypatch):
    set_env(monkeypatch, 1)
    ensure_admin_from_env(db)
    set_env(monkeypatch, None)
    ensure_admin_from_env(db)
    assert admins(db) == []


def test_revoke_admin(db, monkeypatch):
    set_env(monkeypatch, None)
    grant_admin(db, 3, granted_by="cli")
    assert revoke_admin(db, 3) is True
    assert revoke_admin(db, 3) is False
    assert admins(db) == []


def test_list_admins_marks_env(db, monkeypatch):
    set_env(monkeypatch, 2)
    ensure_admin_from_env(db)
    grant_admin(db, 3, granted_by="cli")
    items = {a["user_id"]: a for a in list_admins(db)}
    assert items[2]["is_env_admin"] and not items[3]["is_env_admin"]
    assert items[3]["email"] == "u3@example.com"
