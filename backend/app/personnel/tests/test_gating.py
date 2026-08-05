"""Access-gating integration test — the security boundary of the module.

The module holds third-party PII, so role enforcement is not a feature but a
boundary. The direct-call CRUD tests bypass `require_service`, so this test drives
the real dependency through Starlette's TestClient against a minimal app that
mounts the personnel routers with a real (SQLite) DB and the `hr` service seeded
open to role `employee` only:

    * no token                → 401
    * role without hr access  → 403  (client)
    * employee                → 200
    * admin                   → 200  (owner bypass)
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.users.models  # noqa: F401
import app.services.models  # noqa: F401
import app.personnel.models  # noqa: F401
from app.services.models import Service, ServiceAccess
from app.auth.dependencies import get_current_user
from app.personnel.router import router as personnel_router
from app.personnel.crud import crud_router

GATED_ENDPOINT = "/personnel/rates"  # simplest require_service('hr') route


@pytest.fixture
def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Service(code="hr", title="Кадровые документы", is_enabled=True, sort_order=6))
    db.add(ServiceAccess(service_code="hr", role="employee"))
    db.commit()

    app = FastAPI()
    app.include_router(personnel_router)
    app.include_router(crud_router)
    app.dependency_overrides[get_db] = lambda: db

    def _client(role=None):
        if role is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            user = SimpleNamespace(id=1, email="t@t.kz", full_name="Тест", role=role, is_active=True)
            app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _client
    db.close()


def test_unauthenticated_denied(make_client):
    assert make_client(None).get(GATED_ENDPOINT).status_code == 401


def test_role_without_hr_service_denied(make_client):
    assert make_client("client").get(GATED_ENDPOINT).status_code == 403


def test_employee_allowed(make_client):
    assert make_client("employee").get(GATED_ENDPOINT).status_code == 200


def test_admin_allowed(make_client):
    assert make_client("admin").get(GATED_ENDPOINT).status_code == 200
