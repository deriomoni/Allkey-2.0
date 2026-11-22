"""Раздел 1.1 ТЗ «Закрыто по умолчанию».

* Весь `/api/ops/*` проходит через `OpsGateMiddleware`: без разрешённой роли — 404
  (не 403: наличие раздела не раскрывается).
* Default deny: маршрут без записи в `ROUTE_PERMISSIONS` недоступен никому, даже admin.
* Пока `OPS_REGISTRY_VISIBLE_TO_NON_ADMIN=false`, учитывается только роль admin.
* Роль admin модуля — строка в `user_roles` (role='admin', company_id IS NULL).
  `users.role == 'admin'` сама по себе доступа к модулю НЕ даёт.
* Логи и ответы об ошибках не содержат данных компаний: при исключении пишется только
  класс исключения и имя маршрута.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional, Set

from fastapi import Depends, HTTPException
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
ALL_ROLES = ("admin", "operator", "keyholder", "viewer", "client")

# Явный список: имя маршрута → роли, которым он открыт. Чего нет в списке — 404 всем.
ROUTE_PERMISSIONS: dict[str, Set[str]] = {
    "ops_list_companies": {"admin"},
    "ops_get_company": {"admin"},
    "ops_sync_companies": {"admin"},
    "ops_sync_status": {"admin"},
    "ops_reports_import_preview": {"admin"},
    "ops_reports_import_commit": {"admin"},
    "ops_ui_bundle": {"admin"},
    "ops_list_admins": {"admin"},
    "ops_obligation_create": {"admin"},
    "ops_obligation_confirm": {"admin"},
    "ops_obligation_dismiss": {"admin"},
}

# Белый список полей карточки по ролям (п. 4). None — все поля.
# Для остальных ролей пусто: наполняет владелец отдельным решением.
VISIBLE_FIELDS: dict[str, Optional[frozenset]] = {
    "admin": None,
    "operator": frozenset(),
    "keyholder": frozenset(),
    "viewer": frozenset(),
    "client": frozenset(),
}

NOT_FOUND_BODY = json.dumps({"detail": "Not Found"}).encode()
SERVER_ERROR_BODY = json.dumps({"detail": "Внутренняя ошибка"}, ensure_ascii=False).encode()


def effective_roles(db: Session, user: User) -> Set[str]:
    """Роли модуля, которые реально действуют для пользователя."""
    if not user or not user.is_active:
        return set()
    rows = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()
    roles = set()
    for r in rows:
        if r.role == "admin" and r.company_id is None:
            roles.add("admin")
        elif r.role in ALL_ROLES and r.role != "admin":
            roles.add(r.role)
    if not get_ops_settings().ops_registry_visible_to_non_admin:
        roles &= {"admin"}
    return roles


def is_ops_admin(db: Session, user: User) -> bool:
    return "admin" in effective_roles(db, user)


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

        name = _route_name(fastapi_app, scope) if fastapi_app is not None else None
        allowed = ROUTE_PERMISSIONS.get(name or "", set())
        if not roles or not (roles & allowed):
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
