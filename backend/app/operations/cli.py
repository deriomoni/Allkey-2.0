"""CLI модуля «Операции».

    python -m app.operations.cli sync                 # валидатор + синхронизация карточек
    python -m app.operations.cli sync --skip-validator
    python -m app.operations.cli grant-admin --user-id 1
    python -m app.operations.cli revoke-admin --user-id 1
    python -m app.operations.cli kgd-fetch --out PATH   # API КГД по всем живым карточкам → JSON вне репозитория
    python -m app.operations.cli grant-staff --email user@example.com   # роль «сотрудник» (экран «Компании»)
    python -m app.operations.cli revoke-staff --email user@example.com
    python -m app.operations.cli reports-load --file rows.json  # строки форм в ops_company_reports, только добавление
    python -m app.operations.cli admins               # кому выдана роль admin модуля

Выводит только счётчики и ошибки валидатора — без названий компаний.
"""
import argparse
import sys

from app.database import Base, SessionLocal, engine
import app.users.models  # noqa: F401
from app.operations import models  # noqa: F401
from app.operations.access import grant_admin, grant_staff, list_admins, list_staff, revoke_admin, revoke_staff, user_by_email
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
    rl = sub.add_parser("reports-load")
    rl.add_argument("--file", required=True, help="JSON [{slug, form, period, status, raw_value, source}]")
    gs = sub.add_parser("grant-staff")
    gs.add_argument("--email", required=True)
    rs = sub.add_parser("revoke-staff")
    rs.add_argument("--email", required=True)
    kf = sub.add_parser("kgd-fetch")
    kf.add_argument("--out", required=True, help="файл JSON (вне репозиториев)")
    kf.add_argument("--bins", default="", help="только эти БИН через запятую")
    kf.add_argument("--delay", type=float, default=0.4)
    kf.add_argument("--from-file", default="", help="не ходить в КГД: пересчитать normalized по сохранённому файлу")
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
        if args.cmd == "kgd-fetch":
            from app.operations.kgd_batch import fetch_all, renormalize
            if args.from_file:
                return renormalize(args.from_file, args.out)
            return fetch_all(args.out, [b for b in args.bins.split(",") if b.strip()], args.delay)
        if args.cmd in ("grant-staff", "revoke-staff"):
            u = user_by_email(db, args.email)
            if u is None:
                print("Пользователь с таким email не найден.")
                return 1
            if args.cmd == "grant-staff":
                grant_staff(db, u.id, granted_by="cli")
                print(f"Роль «сотрудник» выдана: user_id={u.id}.")
                return 0
            ok = revoke_staff(db, u.id)
            print("Роль «сотрудник» снята." if ok else "У пользователя не было роли «сотрудник».")
            return 0 if ok else 1
        if args.cmd == "reports-load":
            import json
            from app.operations.reports_import import load_rows
            with open(args.file, encoding="utf-8") as f:
                r = load_rows(db, json.load(f))
            print(f"OK: добавлено {r['created']}, уже были (не тронуты) {r['skipped_existing']}, "
                  f"компания не найдена {r['unknown_company']}, некорректных {r['invalid']}")
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
            for a in list_staff(db):
                print(f"user_id={a['user_id']} {a['email']} role=staff granted_by={a['granted_by']} at={a['granted_at']}")
            return 0
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())
