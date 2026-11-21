"""Синхронизация arty-ops/clients/*/client.yaml → ops_companies.

Перед записью вызывается валидатор репозитория `scripts/validate_cards.py`. Если он
нашёл ошибки — синхронизация не выполняется, ошибки возвращаются вызывающему (UI/CLI).
В лог пишутся только счётчики, без названий и БИН.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import yaml
from sqlalchemy.orm import Session

from app.operations.config import get_ops_settings
from app.operations.models import OpsCompany

logger = logging.getLogger("app.operations")


class SyncConfigError(RuntimeError):
    pass


@dataclass
class SyncResult:
    ok: bool
    validator_ok: bool = True
    validator_errors: List[str] = field(default_factory=list)
    validator_output: str = ""
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    missing_in_repo: int = 0
    total: int = 0
    active: int = 0
    inactive: int = 0
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def repo_path() -> Path:
    raw = (get_ops_settings().arty_ops_path or "").strip()
    if not raw:
        raise SyncConfigError("Не задан ARTY_OPS_PATH в .env")
    p = Path(raw)
    if not (p / "clients").is_dir():
        raise SyncConfigError("В ARTY_OPS_PATH нет папки clients/")
    return p


def run_validator(root: Path) -> tuple[bool, List[str], str]:
    """Запуск валидатора репозитория. Возвращает (ok, строки ошибок, полный вывод)."""
    script = root / "scripts" / "validate_cards.py"
    if not script.is_file():
        return False, ["В репозитории нет scripts/validate_cards.py"], ""
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root), capture_output=True, timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return False, ["Валидатор не уложился в 120 секунд"], ""
    out = (proc.stdout or b"").decode("utf-8", "replace") + (proc.stderr or b"").decode("utf-8", "replace")
    errors = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("ОШИБКА")]
    if proc.returncode != 0 and not errors:
        errors = ["Валидатор завершился с кодом %s" % proc.returncode]
    return proc.returncode == 0, errors, out


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def _date(v) -> Optional[dt.date]:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return None


def _str(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def card_to_columns(slug: str, card: dict) -> dict:
    tax = card.get("tax") or {}
    systems = card.get("systems") or {}
    onec = systems.get("onec") or {}
    drive = systems.get("drive") or {}
    bin_ = card.get("bin")
    return {
        "slug": slug,
        # 218 из 230 карточек пока без официального name (TODO в репозитории) —
        # для отображения берём папку на Диске, затем slug. Признак — в API (name_official).
        "name": _str(card.get("name")) or _str(drive.get("folder_name")) or slug,
        "bin": _str(bin_),
        "aliases": [str(a) for a in (card.get("aliases") or []) if a is not None],
        "card_json": _jsonable(card),
        "tax_regime": _str(tax.get("regime")),
        "vat_payer": tax.get("vat_payer") if isinstance(tax.get("vat_payer"), bool) else None,
        "drive_folder_name": _str(drive.get("folder_name")),
        "drive_root_folder_id": _str(drive.get("root_folder_id")),
        "drive_agent_folder_id": _str(drive.get("agent_folder_id")),
        "onec_kind": _str(onec.get("kind")),
        "onec_url": _str(onec.get("url")),
        "onec_login": _str(onec.get("login")),
        "onec_note": _str(onec.get("note")),
        "run_on": _str(onec.get("run_on")),
        "closed_through": _date(onec.get("closed_through")),
        "responsible_json": _jsonable(card.get("responsible") or {}),
        "active": card.get("active") is not False,
        "inactive_reason": _str(card.get("inactive_reason")),
        "inactive_since": _date(card.get("inactive_since")),
        "missing_in_repo": False,
    }


def load_cards(root: Path) -> List[tuple[str, dict]]:
    cards = []
    for p in sorted((root / "clients").glob("*/client.yaml")):
        slug = p.parent.name
        if slug.startswith("_"):
            continue
        with open(p, encoding="utf-8") as f:
            cards.append((slug, yaml.safe_load(f) or {}))
    return cards


def sync_companies(db: Session, skip_validator: bool = False) -> SyncResult:
    try:
        root = repo_path()
    except SyncConfigError as e:
        return SyncResult(ok=False, error=str(e))

    if not skip_validator:
        ok, errors, out = run_validator(root)
        if not ok:
            logger.warning("ops: sync aborted — validator reported %d error(s)", len(errors))
            return SyncResult(ok=False, validator_ok=False, validator_errors=errors, validator_output=out)

    try:
        cards = load_cards(root)
    except Exception as exc:  # noqa: BLE001
        logger.error("ops: sync failed reading cards (%s)", type(exc).__name__)
        return SyncResult(ok=False, error="Не удалось прочитать карточки (%s)" % type(exc).__name__)

    now = dt.datetime.now(dt.timezone.utc)
    res = SyncResult(ok=True)
    existing = {c.slug: c for c in db.query(OpsCompany).all()}
    seen = set()
    for slug, card in cards:
        cols = card_to_columns(slug, card)
        seen.add(slug)
        obj = existing.get(slug)
        if obj is None:
            db.add(OpsCompany(**cols, synced_at=now))
            res.created += 1
        else:
            changed = any(getattr(obj, k) != v for k, v in cols.items())
            if changed:
                for k, v in cols.items():
                    setattr(obj, k, v)
                res.updated += 1
            else:
                res.unchanged += 1
            obj.synced_at = now
        res.total += 1
        if cols["active"]:
            res.active += 1
        else:
            res.inactive += 1

    for slug, obj in existing.items():
        if slug not in seen and not obj.missing_in_repo:
            obj.missing_in_repo = True
            res.missing_in_repo += 1
    db.commit()
    logger.info(
        "ops: sync done total=%d created=%d updated=%d unchanged=%d missing=%d",
        res.total, res.created, res.updated, res.unchanged, res.missing_in_repo,
    )
    return res
