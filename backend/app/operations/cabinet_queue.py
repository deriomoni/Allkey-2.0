"""Очередь на вход в кабинет налогоплательщика (ops_cabinet_queue) — для knp-watch.

Ставит в очередь владелец (карточка / CLI) или расписание (`schedule`: давно не проверяли).
knp-watch берёт открытые записи (`open_entries`) и после прогона по компании снимает запись (`mark_done`).
Результат проверки knp-watch пишет в карточку (client.yaml → cabinet:), не сюда.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.operations.models import OpsCabinetQueue, OpsCompany

REASONS = ("manual", "schedule", "deadline")
REASON_LABEL = {"manual": "вручную", "schedule": "по расписанию", "deadline": "перед сроком формы"}


class QueueError(ValueError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def open_entry(db: Session, company_id: int) -> Optional[OpsCabinetQueue]:
    return (db.query(OpsCabinetQueue)
            .filter(OpsCabinetQueue.company_id == company_id, OpsCabinetQueue.done_at.is_(None))
            .order_by(OpsCabinetQueue.id).first())


def open_entries(db: Session) -> List[Tuple[OpsCabinetQueue, OpsCompany]]:
    return (db.query(OpsCabinetQueue, OpsCompany)
            .join(OpsCompany, OpsCompany.id == OpsCabinetQueue.company_id)
            .filter(OpsCabinetQueue.done_at.is_(None))
            .order_by(OpsCabinetQueue.requested_at, OpsCabinetQueue.id).all())


def enqueue(db: Session, company: OpsCompany, reason: str = "manual", note: Optional[str] = None,
            by: Optional[str] = None) -> Tuple[OpsCabinetQueue, bool]:
    """Ставит компанию в очередь. Уже стоит — возвращает существующую запись (created=False), вторую не создаёт."""
    if reason not in REASONS:
        raise QueueError(f"причина: {', '.join(REASONS)}")
    if not company.active:
        raise QueueError("компания в архиве — в кабинет не ходим")
    existing = open_entry(db, company.id)
    if existing is not None:
        return existing, False
    e = OpsCabinetQueue(company_id=company.id, reason=reason, note=(note or "").strip()[:500] or None,
                        requested_by=by, requested_at=_now())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e, True


def mark_done(db: Session, entry: OpsCabinetQueue, by: Optional[str] = None, result: Optional[str] = None) -> OpsCabinetQueue:
    if entry.done_at is not None:
        raise QueueError("запись уже снята")
    entry.done_at = _now()
    entry.done_by = by
    entry.result = (result or "").strip()[:500] or None
    db.commit()
    db.refresh(entry)
    return entry


TAKE_TTL = dt.timedelta(hours=2)   # взятая и не снятая запись через 2 ч снова свободна (слушатель упал)


def _aware(v: Optional[dt.datetime]) -> Optional[dt.datetime]:
    return v.replace(tzinfo=dt.timezone.utc) if v is not None and v.tzinfo is None else v


def take(db: Session, entry: OpsCabinetQueue, by: str) -> OpsCabinetQueue:
    """Взять запись в работу. Снята → ошибка; взята другим меньше 2 ч назад → ошибка; тем же исполнителем — ок."""
    if entry.done_at is not None:
        raise QueueError("запись уже снята")
    t = _aware(entry.taken_at)
    if t is not None and entry.taken_by != by and _now() - t < TAKE_TTL:
        raise QueueError("запись уже взята в работу")
    entry.taken_at, entry.taken_by = _now(), by
    db.commit()
    db.refresh(entry)
    return entry


def _checked_at(c: OpsCompany) -> Optional[dt.date]:
    v = ((c.card_json or {}).get("cabinet") or {}).get("checked_at") if isinstance((c.card_json or {}).get("cabinet"), dict) else None
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def schedule_candidates(db: Session, every_days: int = 14, today: Optional[dt.date] = None) -> List[OpsCompany]:
    """Живые компании с ЭЦП, которые не проверялись `every_days` дней (или никогда) и ещё не в очереди."""
    today = today or dt.date.today()
    queued = {e.company_id for e in db.query(OpsCabinetQueue).filter(OpsCabinetQueue.done_at.is_(None))}
    out = []
    for c in db.query(OpsCompany).filter(OpsCompany.active.is_(True), OpsCompany.missing_in_repo.is_(False)).order_by(OpsCompany.name):
        if c.id in queued:
            continue
        if (((c.card_json or {}).get("systems") or {}).get("esign")) == "none":
            continue  # без ключа — в кабинет не ходим (knp-watch, владелец 23.11.2026)
        last = _checked_at(c)
        if last is None or (today - last).days >= every_days:
            out.append(c)
    return out


def entry_dict(e: OpsCabinetQueue, c: Optional[OpsCompany] = None) -> dict:
    d = {
        "id": e.id, "company_id": e.company_id, "reason": e.reason, "reason_label": REASON_LABEL.get(e.reason, e.reason),
        "note": e.note, "requested_by": e.requested_by,
        "requested_at": e.requested_at.isoformat() if e.requested_at else None,
        "taken_at": e.taken_at.isoformat() if e.taken_at else None, "taken_by": e.taken_by,
        "done_at": e.done_at.isoformat() if e.done_at else None, "done_by": e.done_by, "result": e.result,
    }
    if c is not None:
        last = _checked_at(c)
        d |= {"slug": c.slug, "name": c.name, "bin": c.bin, "hidden": bool(c.hidden),
              "checked_at": last.isoformat() if last else None}
    return d
