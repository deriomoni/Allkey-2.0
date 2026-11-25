"""Раздел 1.1 ТЗ «Закрыто по умолчанию».

* Весь `/api/ops/*` проходит через `OpsGateMiddleware`: без разрешённой роли — 404
  (не 403: наличие раздела не раскрывается).
* Default deny: маршрут без записи в `ROUTE_PERMISSIONS` недоступен никому, даже admin.
* Действуют только две роли: `admin` и `staff` (сотрудник, итерация 3 — 24.11.2026). Глобального флага
  видимости нет: доступ даёт только роль в `user_roles`. Прочие строки ролей игнорируются.
* Роль admin модуля — строка в `user_roles` (role='admin', company_id IS NULL).
  `users.role == 'admin'` сама по себе доступа к модулю НЕ даёт.
* Логи и ответы об ошибках не содержат данных компаний: при исключении пишется только
  класс исключения и имя маршрута.
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Iterable, Optional, Set

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.routing import Match

from app.auth.dependencies import get_current_user
from app.auth.jwt import decode_token
from app.database import SessionLocal, get_db
from app.operations.config import get_ops_settings
from app.operations.models import UserRoleAssignment
from app.users.models import User

logger = logging.getLogger("app.operations")

OPS_PREFIX = "/api/ops"
ALL_ROLES = ("admin", "staff", "operator", "keyholder", "viewer", "client")
# Роли, которые реально дают доступ (без company_id). Остальные из ALL_ROLES — зарезервированы ТЗ.
EFFECTIVE_ROLES = ("admin", "staff")

# Явный список: имя маршрута → роли, которым он открыт. Чего нет в списке — 404 всем.
ROUTE_PERMISSIONS: dict[str, Set[str]] = {
    # сотрудник (staff): экран «Компании» — список, фильтры, ссылка на Диск, экспорт
    "ops_list_companies": {"admin", "staff"},
    "ops_sync_status": {"admin", "staff"},
    "ops_ui_bundle": {"admin", "staff"},
    "ops_me": {"admin", "staff"},
    "ops_companies_export": {"admin", "staff"},
    # итерация 4: карточка компании, правка адреса 1С, заметки, флаг «подозрение» (без подтверждения)
    "ops_get_company": {"admin", "staff"},
    "ops_company_onec_update": {"admin", "staff"},
    "ops_company_note_add": {"admin", "staff"},
    # только admin: «Служебное», «скрытая», КГД, подтверждение/снятие флагов
    "ops_sync_companies": {"admin"},
    "ops_reports_import_preview": {"admin"},
    "ops_reports_import_commit": {"admin"},
    "ops_forms_import_preview": {"admin"},
    "ops_forms_import_apply": {"admin"},
    "ops_list_admins": {"admin"},
    "ops_obligation_create": {"admin", "staff"},
    "ops_obligation_confirm": {"admin"},
    "ops_obligation_dismiss": {"admin"},
    "ops_company_set_hidden": {"admin"},
    "ops_kgd_check": {"admin"},
    # исполнитель knp-watch по токену OPS_AGENT_TOKEN (заголовок X-Ops-Agent-Token): только очередь кабинета
    "ops_agent_queue_list": {"agent"},
    "ops_agent_queue_take": {"agent"},
    "ops_agent_queue_done": {"agent"},
    # очередь на вход в кабинет налогоплательщика (knp-watch) — только admin
    "ops_cabinet_queue_list": {"admin"},
    "ops_cabinet_queue_add": {"admin"},
    "ops_cabinet_queue_done": {"admin"},
}

# ТЗ 1.1 п. 9 — скрытые компании. Маршруты, чьи обработчики фильтруют скрытые компании
# через visible_companies()/company_visible(). Маршрут, открытый в ROUTE_PERMISSIONS
# не-admin роли, но отсутствующий здесь, гейт закрывает (404): без фильтра — не открывать.
HIDDEN_SAFE_ROUTES: Set[str] = {
    "ops_list_companies",
    "ops_get_company",
    "ops_sync_status",
    "ops_companies_export",
    "ops_company_onec_update",
    "ops_company_note_add",
    "ops_obligation_create",
    # данных компаний не отдают вовсе
    "ops_ui_bundle",
    "ops_me",
}

# Белый список полей по ролям (п. 4). None — все поля. Сотруднику — колонки экрана «Компании»;
# без признака «скрытая» и без подозрений по обязательствам.
VISIBLE_FIELDS: dict[str, Optional[frozenset]] = {
    "admin": None,
    "staff": frozenset({
        "id", "slug", "name", "name_official", "legal_name", "bin", "aliases", "folder_name",
        "tax_regime", "vat_payer", "vat_date", "forms", "plan_missing", "active", "missing_in_repo", "drive_url",
        # карточка компании (итерация 4) — всё, что в ней есть, кроме _agent и «скрытой» (их вырезает роутер)
        "card", "onec", "inactive_reason", "inactive_since", "drive", "reports", "synced_at", "obligations",
        "staff_notes", "profile", "profile_url",
        # "cabinet" (блок «Кабинет налогоплательщика») сотруднику пока не отдаётся — владелец 24.11.2026, откроем отдельно
    }),
}

NOT_FOUND_BODY = json.dumps({"detail": "Not Found"}).encode()
SERVER_ERROR_BODY = json.dumps({"detail": "Внутренняя ошибка"}, ensure_ascii=False).encode()


def effective_roles(db: Session, user: User) -> Set[str]:
    """Роли модуля, которые реально действуют для пользователя."""
    if not user or not user.is_active:
        return set()
    rows = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()
    return {r.role for r in rows if r.role in EFFECTIVE_ROLES and r.company_id is None}


def is_ops_admin(db: Session, user: User) -> bool:
    return "admin" in effective_roles(db, user)


def sees_hidden(roles: Iterable[str]) -> bool:
    """Скрытые компании (hidden=true) видит только admin модуля."""
    return "admin" in set(roles)


def visible_companies(db: Session, roles: Iterable[str]):
    """Единственная точка выборки компаний для ответов API: не-admin скрытых не получает."""
    from app.operations.models import OpsCompany

    q = db.query(OpsCompany)
    return q if sees_hidden(roles) else q.filter(OpsCompany.hidden.is_(False))


def company_visible(company, roles: Iterable[str]) -> bool:
    return company is not None and (sees_hidden(roles) or not company.hidden)


AGENT_HEADER = b"x-ops-agent-token"
AGENT_MIN_LEN = 32


def agent_token_ok(token: Optional[str]) -> bool:
    """Токен исполнителя совпадает с OPS_AGENT_TOKEN (сравнение за постоянное время). Не задан — False."""
    secret = get_ops_settings().ops_agent_token
    expected = secret.get_secret_value() if secret else ""
    if len(expected) < AGENT_MIN_LEN or not token:
        return False
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def _agent_from_scope(scope) -> bool:
    headers = dict(scope.get("headers") or [])
    raw = headers.get(AGENT_HEADER)
    return agent_token_ok(raw.decode("latin-1") if raw else None)


def route_open_for(name: Optional[str], roles: Set[str]) -> bool:
    """Default deny + п. 9: не-admin проходит только на маршруты, фильтрующие скрытые.
    Роль agent (токен исполнителя) — только на свои маршруты ops_agent_queue_*."""
    allowed = ROUTE_PERMISSIONS.get(name or "", set())
    if not roles or not (roles & allowed):
        return False
    if "admin" in roles & allowed or "agent" in roles & allowed:
        return True
    return (name or "") in HIDDEN_SAFE_ROUTES


def filter_fields(data: dict, roles: Iterable[str]) -> dict:
    """Отдаёт только поля из VISIBLE_FIELDS для лучшей из ролей пользователя."""
    roles = set(roles)
    if "admin" in roles:
        return data
    allowed: set = set()
    for r in roles:
        allowed |= set(VISIBLE_FIELDS.get(r) or ())
    return {k: v for k, v in data.items() if k in allowed}


def _user_from_scope(scope, db: Session) -> Optional[User]:
    headers = dict(scope.get("headers") or [])
    auth = headers.get(b"authorization", b"").decode("latin-1")
    if not auth.lower().startswith("bearer "):
        return None
    payload = decode_token(auth[7:].strip())
    if not payload or not payload.get("sub"):
        return None
    return db.query(User).filter(User.email == payload["sub"]).first()


def _route_name(app, scope) -> Optional[str]:
    for route in app.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "name", None)
    return None


async def _send_json(send, status: int, body: bytes):
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


class OpsGateMiddleware:
    """ASGI-middleware: единая проверка роли для всего /api/ops/*."""

    def __init__(self, app, session_factory=None):
        self.app = app
        self.session_factory = session_factory or SessionLocal

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (
            scope["path"] == OPS_PREFIX or scope["path"].startswith(OPS_PREFIX + "/")
        ):
            await self.app(scope, receive, send)
            return

        fastapi_app = scope.get("app")
        db = self.session_factory()
        try:
            user = _user_from_scope(scope, db)
            roles = effective_roles(db, user) if user else set()
        finally:
            db.close()
        if _agent_from_scope(scope):
            roles = set(roles) | {"agent"}

        name = _route_name(fastapi_app, scope) if fastapi_app is not None else None
        if not route_open_for(name, roles):
            await _send_json(send, 404, NOT_FOUND_BODY)
            return

        started = False

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:  # noqa: BLE001 — намеренно глушим подробности
            # Ни аргументов исключения, ни трейсбека: там могут быть название/БИН/URL базы.
            logger.error("ops: unhandled %s in route %s", type(exc).__name__, name)
            if not started:
                await _send_json(send, 500, SERVER_ERROR_BODY)


async def require_ops_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """admin или staff (вторая линия обороны для маршрутов сотрудника). Иначе 404."""
    if not effective_roles(db, current_user):
        raise HTTPException(status_code=404, detail="Not Found")
    return current_user


async def require_ops_agent(request: Request) -> str:
    """Вторая линия обороны для маршрутов исполнителя: заголовок X-Ops-Agent-Token. Иначе 404."""
    if not agent_token_ok(request.headers.get("x-ops-agent-token")):
        raise HTTPException(status_code=404, detail="Not Found")
    return "knp-watch (агент)"


async def require_ops_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Вторая линия обороны в обработчиках (первая — middleware). Тоже 404."""
    if not is_ops_admin(db, current_user):
        raise HTTPException(status_code=404, detail="Not Found")
    return current_user


def _admin_rows(db: Session):
    return db.query(UserRoleAssignment).filter(
        UserRoleAssignment.role == "admin",
        UserRoleAssignment.company_id.is_(None),
    )


def ensure_admin_from_env(db: Session) -> None:
    """Привести роль admin «из .env» в соответствие с OPS_ADMIN_USER_ID (при старте).

    * OPS_ADMIN_USER_ID получает роль (granted_by='env'), если её у него нет.
    * Роль, выданная ранее через .env другому id, снимается автоматически — так смена
      OPS_ADMIN_USER_ID не оставляет за прежним владельцем доступ.
    * Роль, выданная явно через CLI (granted_by='cli'), не трогается: её снимает только
      `revoke-admin`.
    """
    uid = get_ops_settings().ops_admin_user_id
    stale = [r for r in _admin_rows(db).filter(UserRoleAssignment.granted_by == "env").all() if r.user_id != uid]
    for r in stale:
        logger.info("ops: admin role revoked from user_id %s (OPS_ADMIN_USER_ID changed)", r.user_id)
        db.delete(r)
    if stale:
        db.commit()
    if uid:
        grant_admin(db, uid, granted_by="env")


def grant_admin(db: Session, user_id: int, granted_by: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.warning("ops: admin grant skipped — user_id %s not found", user_id)
        return False
    exists = _admin_rows(db).filter(UserRoleAssignment.user_id == user_id).first()
    if exists is None:
        db.add(UserRoleAssignment(user_id=user_id, role="admin", company_id=None, granted_by=granted_by))
        db.commit()
        logger.info("ops: admin role granted to user_id %s (%s)", user_id, granted_by)
    elif granted_by == "cli" and exists.granted_by != "cli":
        # Явная выдача сильнее .env: после неё смена OPS_ADMIN_USER_ID роль не снимет.
        exists.granted_by = "cli"
        db.commit()
        logger.info("ops: admin role of user_id %s pinned by cli", user_id)
    return True


def revoke_admin(db: Session, user_id: int) -> bool:
    """Снять роль admin модуля. Если это OPS_ADMIN_USER_ID — при следующем старте вернётся."""
    n = _admin_rows(db).filter(UserRoleAssignment.user_id == user_id).delete()
    db.commit()
    if n:
        logger.info("ops: admin role revoked from user_id %s (cli)", user_id)
    return bool(n)


def list_admins(db: Session) -> list:
    env_uid = get_ops_settings().ops_admin_user_id
    out = []
    for r in _admin_rows(db).order_by(UserRoleAssignment.created_at).all():
        u = db.query(User).filter(User.id == r.user_id).first()
        out.append({
            "user_id": r.user_id,
            "email": u.email if u else None,
            "full_name": u.full_name if u else None,
            "is_active": bool(u and u.is_active),
            "granted_by": r.granted_by,
            "granted_at": r.created_at.isoformat() if r.created_at else None,
            "is_env_admin": r.user_id == env_uid,
        })
    return out


# --- Роль «сотрудник» (staff): выдаётся и снимается командами CLI по email -------------------

def user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == (email or "").strip()).first()


def grant_staff(db: Session, user_id: int, granted_by: str = "cli") -> bool:
    if db.query(User).filter(User.id == user_id).first() is None:
        return False
    q = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id,
                                            UserRoleAssignment.role == "staff",
                                            UserRoleAssignment.company_id.is_(None))
    if q.first() is None:
        db.add(UserRoleAssignment(user_id=user_id, role="staff", company_id=None, granted_by=granted_by))
        db.commit()
        logger.info("ops: staff role granted to user_id %s (%s)", user_id, granted_by)
    return True


def revoke_staff(db: Session, user_id: int) -> bool:
    n = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id,
                                            UserRoleAssignment.role == "staff").delete()
    db.commit()
    if n:
        logger.info("ops: staff role revoked from user_id %s (cli)", user_id)
    return bool(n)


def list_staff(db: Session) -> list:
    out = []
    rows = db.query(UserRoleAssignment).filter(UserRoleAssignment.role == "staff",
                                               UserRoleAssignment.company_id.is_(None))
    for r in rows.order_by(UserRoleAssignment.created_at).all():
        u = db.query(User).filter(User.id == r.user_id).first()
        out.append({"user_id": r.user_id, "email": u.email if u else None,
                    "full_name": u.full_name if u else None, "is_active": bool(u and u.is_active),
                    "granted_by": r.granted_by,
                    "granted_at": r.created_at.isoformat() if r.created_at else None})
    return out
