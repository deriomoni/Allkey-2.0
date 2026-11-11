"""Тест доступа — граница безопасности модуля.

В договоре персональные данные третьего лица, поэтому проверка роли — не фича,
а граница. Тест прогоняет реальную зависимость `require_service('selfemployed')`
через TestClient на минимальном приложении с SQLite и сервисом, открытым только
роли `employee`:

    * без токена                      → 401
    * роль без доступа (client)       → 403
    * employee                        → 200
    * admin                           → 200 (владелец видит всё)
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database import Base, get_db
import app.users.models  # noqa: F401
import app.services.models  # noqa: F401
from app.selfemployed.router import router as selfemployed_router
from app.services.models import Service, ServiceAccess

GATED_ENDPOINT = "/api/selfemployed/okeds"


@pytest.fixture
def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Service(code="selfemployed", title="Договор с самозанятым", is_enabled=True, sort_order=8))
    db.add(ServiceAccess(service_code="selfemployed", role="employee"))
    db.commit()

    app = FastAPI()
    app.include_router(selfemployed_router)
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


def test_role_without_service_denied(make_client):
    assert make_client("client").get(GATED_ENDPOINT).status_code == 403


def test_employee_allowed(make_client):
    assert make_client("employee").get(GATED_ENDPOINT).status_code == 200


def test_admin_allowed(make_client):
    assert make_client("admin").get(GATED_ENDPOINT).status_code == 200


def test_okeds_payload_shape(make_client):
    """Справочник отдаётся в порядке ORDER и содержит поля для формы."""
    rows = make_client("admin").get(GATED_ENDPOINT).json()
    assert len(rows) == 12
    assert [r["code"] for r in rows][:2] == ["43310", "43320"]
    assert set(rows[0]) == {"code", "name", "kind", "title", "default_subject", "notice_days"}


def test_generate_returns_docx(make_client):
    """POST /generate отдаёт .docx с кириллическим именем файла; БД не трогается."""
    body = {
        "oked": "43310", "number": "СЗ-1", "contract_date": "2026-10-06",
        "valid_to": "2026-12-31", "amount": 900000,
        "customer": {"org_form": "ТОО", "name": "Тест", "bin": "210940012346",
                     "head_name": "Иванов Иван Иванович"},
        "executor": {"full_name": "Нурланов Ерлан Бакытович", "iin": "900515300127"},
    }
    r = make_client("admin").post("/api/selfemployed/generate", json=body)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert r.content[:2] == b"PK"


def test_validate_iin_and_bin(make_client):
    """Проверки ИИН/БИН — хелперы кадрового модуля, свой эндпоинт (не /personnel)."""
    client = make_client("admin")
    ok = client.post("/api/selfemployed/validate/iin", json={"iin": "900515300127"}).json()
    assert ok["valid"] and ok["gender"] == "male" and ok["birth_date"] == "1990-05-15"
    bad = client.post("/api/selfemployed/validate/iin", json={"iin": "900515300123"}).json()
    assert bad["valid"] is False
    assert client.post("/api/selfemployed/validate/bin", json={"bin": "210940012346"}).json()["valid"]
    assert client.post("/api/selfemployed/validate/bin", json={"bin": "210940012345"}).json()["valid"] is False


def test_unknown_oked_rejected(make_client):
    body = {
        "oked": "00000", "valid_to": "2026-12-31", "amount": 1000,
        "customer": {"name": "Тест", "bin": "210940012346", "head_name": "Иванов Иван Иванович"},
        "executor": {"full_name": "Нурланов Ерлан Бакытович", "iin": "900515300127"},
    }
    assert make_client("admin").post("/api/selfemployed/check", json=body).status_code == 422
