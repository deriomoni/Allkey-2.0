"""Пакетная выборка API КГД по живым карточкам allkey-ops (`cli kgd-fetch`).

Порядок: сначала карточки с пустым режимом или НДС, затем остальные. Результат — JSON
{"fetched_at", "items": [{slug, bin, ok, raw|error}]} в файл вне репозиториев: применяет его
к карточкам скрипт allkey-ops `scripts/kgd_apply.py`. Токен в файл не пишется.
Печатает только счётчики.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import List

from app.operations.kgd import KgdError, fetch_raw
from app.operations.sync import load_cards, repo_path


def active_cards_in_order(root: Path):
    cards = []
    for slug, card in load_cards(root):
        if card.get("active") is False:
            continue
        tax = card.get("tax") or {}
        empty = tax.get("regime") is None or tax.get("vat_payer") is None
        cards.append((0 if empty else 1, slug, str(card.get("bin") or "").strip()))
    return [(slug, b) for _, slug, b in sorted(cards)]


def fetch_all(out: str, only_bins: List[str], delay: float = 0.4) -> int:
    root = repo_path()
    todo = active_cards_in_order(root)
    if only_bins:
        todo = [(s, b) for s, b in todo if b in set(only_bins)]
    items, ok, err = [], 0, 0
    for i, (slug, b) in enumerate(todo):
        if not b:
            items.append({"slug": slug, "bin": None, "ok": False, "error": "в карточке нет БИН"})
            err += 1
            continue
        try:
            items.append({"slug": slug, "bin": b, "ok": True, "raw": fetch_raw(b)})
            ok += 1
        except KgdError as e:
            items.append({"slug": slug, "bin": b, "ok": False, "error": str(e)})
            err += 1
        if delay and i < len(todo) - 1:
            time.sleep(delay)
    Path(out).write_text(json.dumps({"fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                                     "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"КГД: запрошено {len(todo)}, ответов {ok}, ошибок {err}")
    return 0 if ok else 1
