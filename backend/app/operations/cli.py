"""CLI модуля «Операции».

    python -m app.operations.cli sync                 # валидатор + синхронизация карточек
    python -m app.operations.cli sync --skip-validator
    python -m app.operations.cli grant-admin --user-id 1
    python -m app.operations.cli admins               # кому выдана роль admin модуля

Выводит только счётчики и ошибки валидатора — без названий компаний.
"""
import argparse
import sys

from app.database import Base, SessionLocal, engine
import app.users.models  # noqa: F401
from app.operations import models  # noqa: F401
from app.operations.access import grant_admin
from app.operations.models import UserRoleAssignment
from app.operations.sync import sync_companies


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.operations.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--skip-validator", action="store_true")
    g = sub.add_parser("grant-admin")
    g.add_argument("--user-id", type=int, required=True)
    sub.add_parser("admins")
    args = ap.parse_args(argv)

    Base.metadata.create_all(bind=engine)
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
        if args.cmd == "grant-admin":
            return 0 if grant_admin(db, args.user_id, granted_by="cli") else 1
        if args.cmd == "admins":
            for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.role == "admin").all():
                print(f"user_id={r.user_id} granted_by={r.granted_by} at={r.created_at}")
            return 0
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())
