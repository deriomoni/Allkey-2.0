"""CLI модуля «Операции».

    python -m app.operations.cli sync                 # валидатор + синхронизация карточек
    python -m app.operations.cli sync --skip-validator
    python -m app.operations.cli grant-admin --user-id 1
    python -m app.operations.cli revoke-admin --user-id 1
    python -m app.operations.cli load-plan            # reports/plan-2026.csv → ops_company_reports (source=plan)
    python -m app.operations.cli admins               # кому выдана роль admin модуля

Выводит только счётчики и ошибки валидатора — без названий компаний.
"""
import argparse
import sys

from app.database import Base, SessionLocal, engine
import app.users.models  # noqa: F401
from app.operations import models  # noqa: F401
from app.operations.access import grant_admin, list_admins, revoke_admin
from app.operations.config import get_ops_settings
from app.operations.sync import sync_companies
from app.operations.schema_sync import ensure_ops_schema


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.operations.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--skip-validator", action="store_true")
    g = sub.add_parser("grant-admin")
    g.add_argument("--user-id", type=int, required=True)
    rv = sub.add_parser("revoke-admin")
    rv.add_argument("--user-id", type=int, required=True)
    sub.add_parser("admins")
    sub.add_parser("load-plan")
    args = ap.parse_args(argv)

    Base.metadata.create_all(bind=engine)
    ensure_ops_schema(engine)
    db = SessionLocal()
    try:
        if args.cmd == "sync":
            r = sync_companies(db, skip_validator=args.skip_validator)
            if not r.ok:
                print("Синхронизация не выполнена.")
                if r.error:
                    print(r.error)
                for e in r.validator_errors:
                    print(e)
                return 1
            print(f"OK: всего {r.total} (активных {r.active}, архивных {r.inactive}); "
                  f"новых {r.created}, изменено {r.updated}, без изменений {r.unchanged}, "
                  f"пропало из репозитория {r.missing_in_repo}")
            return 0
        if args.cmd == "load-plan":
            from app.operations.plan import PlanError, load_plan_from_repo
            try:
                r = load_plan_from_repo(db)
            except PlanError as e:
                print(f"План не загружен: {e}")
                return 1
            print(f"OK: новых {r['created']}, обновлено {r['updated']}, совпало с историей (пропущено) "
                  f"{r['conflicts_with_history']}, компания не найдена {r['unknown_company']}, "
                  f"некорректных {r['invalid']}")
            return 0
        if args.cmd == "grant-admin":
            return 0 if grant_admin(db, args.user_id, granted_by="cli") else 1
        if args.cmd == "revoke-admin":
            ok = revoke_admin(db, args.user_id)
            print("Роль снята." if ok else "У пользователя не было роли admin модуля.")
            if ok and get_ops_settings().ops_admin_user_id == args.user_id:
                print("Внимание: это OPS_ADMIN_USER_ID — при следующем старте роль вернётся. Смените id в .env.")
            return 0 if ok else 1
        if args.cmd == "admins":
            for a in list_admins(db):
                env = " [OPS_ADMIN_USER_ID]" if a["is_env_admin"] else ""
                print(f"user_id={a['user_id']} {a['email']} granted_by={a['granted_by']} at={a['granted_at']}{env}")
            return 0
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())
