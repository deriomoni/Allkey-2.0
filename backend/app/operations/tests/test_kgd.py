"""API КГД «Сведения по контрагентам»: клиент, нормализация, гейт, токен не утекает."""
import io
import json
import logging
import urllib.error

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.database import Base, get_db
import app.users.models  # noqa: F401
from app.users.models import User
from app.operations import access, kgd
from app.operations.access import OpsGateMiddleware
from app.operations.config import get_ops_settings
from app.operations.models import UserRoleAssignment
from app.operations.router import ext_router, router

TOKEN = "tok-SECRET-0000"
# Фактический вид ответа (плоские строки), МБИ ИП 23.11.2026 — без лишних полей
FLAT = {
    "actuality": "2026-11-19", "xin": "890404300456", "name": "Центр Бизнес Услуг МБИ", "regDate": "2015-05-20",
    "residency": "Резидент", "oked": "53200", "okedName": "Прочая почтовая и курьерская деятельность",
    "okedDate": "2019-09-10", "vatInfo": "Нет данных", "vatDate": None, "taxMode": "Общеустановленный порядок",
    "taxModeDate": "2026-01-01", "inactive": "Нет данных", "bankrupt": "Нет данных", "regAddressAbsent": "Нет данных",
    "taxDebt": -120.5, "taxDebt1": 0.0, "taxDebt2": 0.0, "taxDebt3": 0.0, "taxDebt4": 0.0,
    "statistics": [{"year": 2025, "workersCount": 2, "taxIn": 1.0, "knn": "2.7", "knnAvg": "2.3", "vatAmount": 0.0},
                   {"year": 2026, "workersCount": 1, "taxIn": 1.0, "knn": "0.0", "knnAvg": "0.0", "vatAmount": 0.0}],
}
# Вид из инструкции КГД ({ru, kk})
NESTED = {
    "xin": "071140005693", "name": {"ru": "Тест", "kk": "Тест"},
    "taxMode": {"ru": "Специальный налоговый режим на основе упрощенной декларации", "kk": "…"},
    "taxModeDate": "2023-09-14", "vatInfo": {"ru": "Нет данных", "kk": "Мәлімет жоқ"}, "vatDate": None,
    "regAddressAbsent": {"ru": "Да", "kk": "Иә"}, "inactive": {"ru": "Нет данных", "kk": "…"},
    "taxDebt": 15000.5, "taxDebt1": 0.0,
}


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def http(monkeypatch):
    calls = []
    state = {"reply": FLAT, "code": 200}

    def fake_urlopen(req, timeout=0):
        calls.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data)})
        if state["code"] != 200:
            raise urllib.error.HTTPError(req.full_url, state["code"], "x", {}, io.BytesIO(b"{}"))
        return _Resp(json.dumps(state["reply"], ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr(kgd.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(get_ops_settings(), "kgd_api_token", SecretStr(TOKEN))
    return calls, state


def test_request_shape(http):
    calls, _ = http
    kgd.fetch_raw("890404300456")
    c = calls[0]
    assert c["url"] == "https://kgd.gov.kz/services/isnaportal/public/get-sur-data"
    assert c["body"] == {"xin": "890404300456"}
    assert c["headers"]["X-portal-token"] == TOKEN


def test_normalize_flat_mbi():
    n = kgd.normalize(FLAT)
    assert (n["regime"], n["ogd_reg_date"], n["vat_payer"]) == ("general", "2026-01-01", False)
    assert n["risks"] == {} and n["status"] == "нет признаков риска"
    # переплата — не задолженность
    assert (n["has_debt"], n["overpayment"]) == (False, True)
    assert n["headcount"] == {2025: 2, 2026: 1} and n["knn"][2025] == {"knn": "2.7", "knn_avg": "2.3"}


def test_normalize_nested_with_risk_and_debt():
    n = kgd.normalize(NESTED)
    assert n["name"] == "Тест" and n["regime"] == "simplified"
    assert list(n["risks"]) == ["regAddressAbsent"] and n["status"] == "есть признаки риска"
    assert n["has_debt"] is True and n["tax_debt"]["taxDebt"] == 15000.5


@pytest.mark.parametrize("info,date,expected", [
    ("Нет данных", None, False), ("", None, False), ("Плательщик НДС", "2025-03-05", True), ("Да", "2025-03-05", True),
    ("Да", None, True),
    ("Снят с учёта по НДС", "2024-01-01", False), ("что-то новое", None, None),
])
def test_vat_mapping(info, date, expected):
    assert kgd.vat_payer(info, date) is expected


@pytest.mark.parametrize("mode,expected", [
    ("Общеустановленный порядок", "general"),
    ("Специальный налоговый режим на основе упрощенной декларации", "simplified"),
    ("Специальный налоговый режим розничного налога", "retail"),
    ("Специальный налоговый режим для крестьянских или фермерских хозяйств", None),
    ("Нет данных", None),
])
def test_regime_mapping(mode, expected):
    assert kgd.regime_code(mode) == expected


def test_errors_do_not_leak_token(http):
    _, state = http
    state["code"] = 401
    with pytest.raises(kgd.KgdError) as e:
        kgd.fetch_raw("890404300456")
    assert TOKEN not in str(e.value) and "890404300456" not in str(e.value)
    with pytest.raises(kgd.KgdError) as e:
        kgd.fetch_raw("12345")
    assert e.value.status == 400


def test_no_token_configured(monkeypatch):
    monkeypatch.setattr(get_ops_settings(), "kgd_api_token", None)
    with pytest.raises(kgd.KgdError) as e:
        kgd.fetch_raw("890404300456")
    assert e.value.status == 409


def test_access_log_mask():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1", "GET", "/api/ops/kgd/check?bin=890404300456", "1.1", 200), None)
    kgd.MaskBinInAccessLog().filter(rec)
    assert "890404300456" not in rec.getMessage() and "bin=***" in rec.getMessage()


@pytest.fixture
def api(monkeypatch, http):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    owner = User(email="owner@t.kz", hashed_password="x", full_name="В", role="admin", is_active=True)
    emp = User(email="emp@t.kz", hashed_password="x", full_name="С", role="employee", is_active=True)
    db.add_all([owner, emp])
    db.commit()
    db.add(UserRoleAssignment(user_id=owner.id, role="admin"))
    db.commit()
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
    h = lambda u: {"Authorization": "Bearer " + create_access_token({"sub": u.email})}  # noqa: E731
    yield client, h(owner), h(emp)
    db.close()


def test_endpoint_admin_only(api):
    client, owner, emp = api
    r = client.get("/api/ops/kgd/check?bin=890404300456", headers=owner)
    assert r.status_code == 200
    body = r.json()
    assert body["normalized"]["regime"] == "general" and TOKEN not in r.text
    assert client.get("/api/ops/kgd/check?bin=890404300456", headers=emp).status_code == 404
    assert client.get("/api/ops/kgd/check?bin=890404300456").status_code == 404
    assert client.get("/api/ops/kgd/check?bin=123", headers=owner).status_code == 400
