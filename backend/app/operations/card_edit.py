"""Переключатель «скрытая» (ТЗ 1.1 п. 9): запись `hidden` в client.yaml коммитом от системы.

Механизм тот же, что у решений по обязательствам (`obligations.py`): правка текстовая — меняется
или добавляется только строка `hidden:`, остальной файл и комментарии не трогаются; проверка,
что YAML после правки отличается от исходного ровно полем hidden; валидатор репозитория по этой
карточке; при ошибке файл возвращается как был. Карточку с незакоммиченными чужими правками
не трогаем. В отличие от обязательств, работает и для архивных карточек.

В лог — только sha коммита (раздел 1.1 ТЗ).
"""
from __future__ import annotations

import logging
import re

import yaml

from app.operations.obligations import (
    ObligationError, _card_path, _git, _lock, _run_validator, check_branch, commit_and_push,
)
from app.operations.sync import repo_path

logger = logging.getLogger("app.operations")

HIDDEN_RE = re.compile(r"^hidden:[^\n#]*(#.*)?$", re.M)


def set_hidden_text(text: str, value: bool) -> str:
    """Та же правка, что `scripts/set_hidden.py` в allkey-ops."""
    v = "true" if value else "false"
    m = HIDDEN_RE.search(text)
    if m:
        comment = ("   " + m.group(1)) if m.group(1) else ""
        new = text[:m.start()] + f"hidden: {v}{comment}" + text[m.end():]
    else:
        lines = text.split("\n")
        at = next((i for i, ln in enumerate(lines) if ln.startswith("inactive_since:")), None)
        if at is None:
            new = text.rstrip("\n") + f"\nhidden: {v}\n"
        else:
            lines.insert(at + 1, f"hidden: {v}")
            new = "\n".join(lines)
    try:
        before, after = yaml.safe_load(text) or {}, yaml.safe_load(new) or {}
    except Exception:  # noqa: BLE001
        raise ObligationError("Не удалось корректно записать карточку", 500)
    before["hidden"] = value
    if before != after:
        raise ObligationError("Не удалось корректно записать карточку", 500)
    return new


def set_hidden(slug: str, value: bool, user_label: str) -> str:
    root = repo_path()
    path = _card_path(root, slug)
    rel = path.relative_to(root).as_posix()
    with _lock:
        check_branch(root)
        dirty = _git(root, "status", "--porcelain", "--", rel)
        if dirty.returncode != 0:
            raise ObligationError("Репозиторий arty-ops недоступен (git)", 500)
        if dirty.stdout.strip():
            raise ObligationError("В карточке есть незакоммиченные правки — сначала закоммитьте их в arty-ops", 409)
        original = path.read_text(encoding="utf-8")
        if (yaml.safe_load(original) or {}).get("hidden") is value:
            return _git(root, "rev-parse", "--short", "HEAD").stdout.decode().strip()  # уже так
        text = set_hidden_text(original, value)
        path.write_text(text, encoding="utf-8", newline="\n")
        err = _run_validator(root, slug)
        if err:
            path.write_text(original, encoding="utf-8", newline="\n")
            raise ObligationError("Валидатор карточек отклонил изменение: " + err, 422)
        msg = f"hidden: {slug} — {'скрыта' if value else 'открыта'} (admin {user_label})"
        sha = commit_and_push(root, path, rel, original, msg)
        logger.info("ops: hidden committed %s", sha)
        return sha
