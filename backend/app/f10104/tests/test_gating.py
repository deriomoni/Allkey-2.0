"""Access-gating integration test — the security boundary of the module.

Same shape as app/personnel/tests/test_gating.py. Первую версию проверяет
ТОЛЬКО владелец: роль `employee` доступа не имеет (решение владельца от
20.08.2026, `SEED_SERVICES` → `roles: []`). Проверка обязана держаться на
HTTP-слое, а не только в интерфейсе. Минимальное приложение монтирует роутер
f10104 к настоящей (SQLite) базе, где сервис заведён БЕЗ выданных ролей:

    * без токена                 → 401
    * client                     → 403
    * employee                   → 403  ← роль снята намеренно
    * admin                      → 200  (владелец видит beta и без роли)

Открытие сотрудникам позже — выдача роли на экране «Доступы», не правка кода:
`seed_services` существующие сервисы не обновляет.

Отдаём 403, а не 404: так работает общий гейт проекта, и менять его поведение
ради внутренней беты не стали (см. ZADANIE-101-04.md, фаза 0.1).
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
from app.services.models import Service, ServiceAccess
from app.auth.dependencies import get_current_user
from app.f10104.router import router as f10104_router
from app.personnel.rates import get_rates

GATED_ENDPOINT = "/f10104/meta"


@pytest.fixture
def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Service(code="f10104", title="Помогайка по форме 101.04", is_enabled=True, sort_order=5))
    # Записи ServiceAccess нет намеренно: ни одна роль доступа не имеет.
    # Если она здесь появится, тесты ниже покраснеют — и это правильно.
    db.commit()

    app = FastAPI()
    app.include_router(f10104_router)
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


def test_role_without_f10104_service_denied(make_client):
    assert make_client("client").get(GATED_ENDPOINT).status_code == 403


def test_employee_denied(make_client):
    """Отдельный тест именно на `employee`: роль снята сознательно, и её
    случайное возвращение в SEED_SERVICES должно покраснеть здесь, а не
    обнаружиться тем, что модуль увидели те, кому его не открывали."""
    assert make_client("employee").get(GATED_ENDPOINT).status_code == 403


def test_seed_entry_grants_no_roles():
    """Та же проверка на уровне данных: запись в реестре ролей не выдаёт."""
    from app.services.router import SEED_SERVICES  # noqa: PLC0415

    entry = next(x for x in SEED_SERVICES if x["code"] == "f10104")
    assert entry["roles"] == []
    assert entry["status"] == "beta"


def test_admin_allowed(make_client):
    assert make_client("admin").get(GATED_ENDPOINT).status_code == 200


def test_meta_reports_loaded_refbooks(make_client):
    """Заодно проверяем, что справочник читается и константы берутся из rates.py."""
    body = make_client("admin").get(GATED_ENDPOINT).json()
    assert body["rules_version"]
    assert body["refbooks"]["income_codes"] == 68
    assert body["refbooks"]["offshore_list"] == 56
    assert body["constants"]["source"] == "app/personnel/rates.py"
    # Сверяем с общим справочником ставок, а не с числом: literal здесь был бы
    # ровно тем вторым источником истины, который модуль и запрещает.
    assert body["constants"]["mrp"] == get_rates().mrp


# ── Расчётные роуты закрыты тем же гейтом ─────────────────────────────────
# Тело подобрано так, чтобы курс НБ РК не понадобился: договор в долларах,
# сети в тесте нет.

EVALUATE_BODY = {
    "answers": {
        "S1.1": {"quarter": 3, "year": 2026},
        "S1.3": "yes",
        "S1.4": "yes",
        "S1.5": "USD",
        "S2.1": "payment",
        "S2.2": "legal_entity",
        "S2.3": "DE",
        "S4.1": "2026-07-10",
        "S4.2": "2026-07-20",
        "S4.4": 10000.0,
        "S4.5": 500.0,
        "S5.1": "services",
        "S5.5": "consulting",
        "S6.1": "outside",
        "S7.2": "no",
    }
}


def test_evaluate_unauthenticated_denied(make_client):
    assert make_client(None).post("/f10104/evaluate", json=EVALUATE_BODY).status_code == 401


def test_evaluate_role_without_service_denied(make_client):
    assert make_client("client").post("/f10104/evaluate", json=EVALUATE_BODY).status_code == 403


def test_evaluate_owner_allowed(make_client):
    response = make_client("admin").post("/f10104/evaluate", json=EVALUATE_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["kpn"]["amount_kzt"] == 1_000_000        # 10 000 × 500 × 20 %
    assert body["rules_version"]
    assert body["graphs"]["F"] == "1033"


def test_aggregate_unauthenticated_denied(make_client):
    body = {"operations": [EVALUATE_BODY["answers"]]}
    assert make_client(None).post("/f10104/aggregate", json=body).status_code == 401


def test_aggregate_role_without_service_denied(make_client):
    body = {"operations": [EVALUATE_BODY["answers"]]}
    assert make_client("client").post("/f10104/aggregate", json=body).status_code == 403


def test_aggregate_owner_allowed(make_client):
    body = {"operations": [EVALUATE_BODY["answers"], EVALUATE_BODY["answers"]]}
    response = make_client("admin").post("/f10104/aggregate", json=body)

    assert response.status_code == 200
    lines = response.json()["lines"]
    assert lines["101.04.002"]["I"] == 2_000_000        # две одинаковые операции
    assert lines["101.04.002"]["IV"] == 2_000_000


def test_evaluate_rejects_broken_date(make_client):
    """Битая дата — это 400 с понятным текстом, а не 500."""
    broken = {"answers": {**EVALUATE_BODY["answers"], "S4.2": "20.07.2026"}}
    response = make_client("admin").post("/f10104/evaluate", json=broken)

    assert response.status_code == 400
    assert "S4.2" in response.json()["detail"]


def test_evaluate_returns_flag_texts(make_client):
    """Тексты флагов приходят вместе с вердиктом: формулировки живут в данных,
    фронтенд их не собирает сам."""
    offshore = {"answers": {**EVALUATE_BODY["answers"], "S2.3": "OFF54"}}
    body = make_client("admin").post("/f10104/evaluate", json=offshore).json()

    detail = {f["code"]: f for f in body["flags_detail"]}
    assert "F-OFFSHORE" in detail
    assert detail["F-OFFSHORE"]["severity"] == "high"
    assert detail["F-OFFSHORE"]["text"]


# ── Справочники для интерфейса ────────────────────────────────────────────

def test_refbooks_unauthenticated_denied(make_client):
    assert make_client(None).get("/f10104/refbooks").status_code == 401


def test_refbooks_role_without_service_denied(make_client):
    assert make_client("client").get("/f10104/refbooks").status_code == 403


def test_refbooks_marks_offshore_convention_and_eaeu(make_client):
    """Налоговые признаки страны считает сервер, не интерфейс."""
    body = make_client("admin").get("/f10104/refbooks").json()
    by_key = {c["key"]: c for c in body["countries"]}

    assert by_key["OFF54"]["is_offshore"] is True
    assert by_key["OFF54"]["offshore_no"] == 54
    assert by_key["OFF54"]["has_convention"] is False   # ст. 682 п. 2
    assert by_key["DE"]["has_convention"] is True
    assert by_key["TH"]["has_convention"] is False      # конвенции с Таиландом нет
    assert by_key["RU"]["is_eaeu"] is True
    assert by_key["DE"]["is_eaeu"] is False


def test_refbooks_carry_flag_texts_for_live_warnings(make_client):
    """Предупреждения по ходу визарда берут текст отсюда, а не из фронтенда."""
    body = make_client("admin").get("/f10104/refbooks").json()

    assert body["flags"]["F-OFFSHORE"]["text"]
    assert body["flags"]["F-VAT-THRESHOLD"]["severity"] == "info"
    assert any(k["group"] == "A" for k in body["service_kinds"])
    assert "KZT" in body["currencies"]
    # Исключения ст. 454 п. 3 — чек-лист шага S9, формулировки из справочника.
    assert any(e["id"] == "art474" for e in body["vat_exemptions"])


def test_evaluate_returns_the_explanation_block(make_client):
    """Блок 2 приходит вместе с вердиктом: отдельного запроса за объяснением
    нет — иначе экран мог бы показать расчёт без причин или причины от другого
    набора ответов."""
    response = make_client("admin").post("/f10104/evaluate", json={
        "answers": {
            "S1.1": {"quarter": 1, "year": 2026}, "S1.4": "yes", "S1.5": "KZT",
            "S2.1": "payment", "S2.2": "legal_entity", "S2.3": "RU",
            "S3.1": "no", "S3.4": "none",
            "S5.1": "dividends", "S5.8": {"share_pct": 70,
                                          "position": "pp5_15pct",
                                          "position_basis": "письмо КГД № 1"},
            "S7.2": "no",
            "S4.1": "2026-03-10", "S4.2": "2026-03-20",
            "S4.4": 7000000, "S4.5": 1,
        },
        "as_of_date": "2026-03-31",
    })

    assert response.status_code == 200
    payload = response.json()
    explanation = payload["explanation"]

    assert explanation["applied"] and explanation["not_applied"]
    assert payload["kpn"]["amount_kzt"] == 1_050_000
    # Сырой журнал развилок фронту не отдаётся: он уже разобран в explanation.
    assert "decisions" not in payload
    # Последняя строка расчёта совпадает с суммой вердикта.
    kpn_line = [c for c in explanation["calc"] if c["label"].startswith("КПН")]
    assert kpn_line and kpn_line[0]["value_kzt"] == 1_050_000
