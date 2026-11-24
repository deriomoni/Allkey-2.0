"""Правки карточки из панели, доступные сотруднику (итерация 4, 24.11.2026).

* адрес базы 1С — `systems.onec.url / kind / note` с обязательной причиной; отметка
  `systems.onec.edited: {by, at, reason}` пишется в карточку (кто/когда/почему);
* заметки — блок `staff_notes` (общая или к форме/периоду), только добавление, с автором и датой.

Механизм тот же, что у решений администратора: текстовая правка (остальной файл и комментарии
не трогаются), сторож «изменилось только то, что должно», валидатор, коммит от системы в ветку
`prod-decisions` с email автора в сообщении, push. В лог — только sha.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Optional

import yaml

from app.operations.obligations import (
    ObligationError, _card_path, _git, _lock, _replace_block, _run_validator, check_branch, commit_and_push,
)
from app.operations.sync import repo_path

logger = logging.getLogger("app.operations")

ONEC_KINDS = ("cloud", "local", "none")
MAX_TEXT = 2000


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="minutes")


def _edit(slug: str, transform, message: str, allowed_changes) -> str:
    """Общий цикл правки: прочитать → transform(text, card) → сторож → валидатор → коммит/push."""
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
        card = yaml.safe_load(original) or {}
        text = transform(original, card)
        try:
            after = yaml.safe_load(text) or {}
        except Exception:  # noqa: BLE001
            raise ObligationError("Не удалось корректно записать карточку", 500)
        if allowed_changes(card) != allowed_changes(after):
            raise ObligationError("Не удалось корректно записать карточку", 500)
        if text == original:
            return _git(root, "rev-parse", "--short", "HEAD").stdout.decode().strip()
        path.write_text(text, encoding="utf-8", newline="\n")
        err = _run_validator(root, slug)
        if err:
            path.write_text(original, encoding="utf-8", newline="\n")
            raise ObligationError("Валидатор карточек отклонил изменение: " + err, 422)
        sha = commit_and_push(root, path, rel, original, message)
        logger.info("ops: staff edit committed %s", sha)
        return sha


# --- 1С ------------------------------------------------------------------------------------

def _yaml_scalar(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)  # JSON-строка — валидный YAML-скаляр


def _set_onec_line(lines: list, start: int, end: int, key: str, value_text: str, comment: str) -> int:
    """Заменить/добавить `    key: value` внутри блока onec (lines[start:end]). Возвращает новый end."""
    pat = re.compile(r"^    " + re.escape(key) + r":")
    for i in range(start + 1, end):
        if pat.match(lines[i]):
            head = f"    {key}: {value_text}"
            lines[i] = head.ljust(38) + ("   " if len(head) >= 37 else "") + f"# {comment}" if comment else head
            return end
    head = f"    {key}: {value_text}"
    lines.insert(start + 1, head.ljust(38) + ("   " if len(head) >= 37 else "") + f"# {comment}" if comment else head)
    return end + 1


def set_onec(slug: str, url: Optional[str], kind: Optional[str], note: Optional[str], reason: str,
             user_label: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ObligationError("Укажите причину изменения")
    if kind is not None and kind not in ONEC_KINDS:
        raise ObligationError("Тип базы: cloud, local или none")
    if url is not None:
        url = url.strip()
        if url and not re.match(r"^https?://\S+$", url):
            raise ObligationError("Адрес базы — ссылка вида https://…")
    if note is not None:
        note = note.strip()[:MAX_TEXT]
    if url is None and kind is None and note is None:
        raise ObligationError("Нечего менять")
    at = dt.date.today().isoformat()
    tag = f"изменил {user_label} {at}"

    def transform(text: str, card: dict) -> str:
        lines = text.split("\n")
        start = next((i for i, ln in enumerate(lines) if re.match(r"^  onec:", ln)), None)
        if start is None:
            raise ObligationError("В карточке нет блока systems.onec — обновите карточку по шаблону", 409)
        end = start + 1
        while end < len(lines) and lines[end].startswith("    "):
            end += 1
        cur = (card.get("systems") or {}).get("onec") or {}
        if url is not None and url != (cur.get("url") or ""):
            end = _set_onec_line(lines, start, end, "url", _yaml_scalar(url), tag)
        if kind is not None and kind != cur.get("kind"):
            end = _set_onec_line(lines, start, end, "kind", kind, tag)
        if note is not None and note != (cur.get("note") or ""):
            end = _set_onec_line(lines, start, end, "note", _yaml_scalar(note), tag)
        edited = "{" + f"by: {_yaml_scalar(user_label)}, at: {_yaml_scalar(_now())}, reason: {_yaml_scalar(reason[:500])}" + "}"
        end = _set_onec_line(lines, start, end, "edited", edited, "")
        return "\n".join(lines)

    def allowed(card: dict):
        c = json.loads(json.dumps(card, default=str))
        onec = ((c.get("systems") or {}).get("onec") or {})
        for k in ("url", "kind", "note", "edited"):
            onec.pop(k, None)
        return c

    return _edit(slug, transform, f"onec: {slug} — адрес/тип/заметка базы 1С изменены ({user_label}): {reason[:120]}",
                 allowed)


# --- заметки -------------------------------------------------------------------------------

def add_note(slug: str, text: str, user_label: str, form: Optional[str] = None, period: Optional[str] = None) -> str:
    text = (text or "").strip()
    if len(text) < 2:
        raise ObligationError("Текст заметки пустой")
    text = text[:MAX_TEXT]
    form = (form or "").strip()[:40] or None
    period = (period or "").strip()[:20] or None
    entry = {"at": _now(), "author": user_label, "text": text}
    if form:
        entry = {"at": entry["at"], "author": user_label, "form": form, "period": period, "text": text}

    def transform(src: str, card: dict) -> str:
        notes = list(card.get("staff_notes") or []) + [entry]
        if re.search(r"^staff_notes:", src, re.M):
            return _replace_block(src, r"^staff_notes:", "staff_notes:", notes, 2)
        block = "# --- Заметки сотрудников из панели Allkey (только добавление; автор и дата) ---\nstaff_notes: []\n"
        lines = src.split("\n")
        i = next((k for k, ln in enumerate(lines) if re.match(r"^# --- Обязательства|^obligation_flags:", ln)), None)
        src2 = ("\n".join(lines[:i]) + "\n" + block + "\n" + "\n".join(lines[i:])) if i is not None \
            else src.rstrip("\n") + "\n\n" + block
        return _replace_block(src2, r"^staff_notes:", "staff_notes:", notes, 2)

    def allowed(card: dict):
        c = json.loads(json.dumps(card, default=str))
        notes = c.pop("staff_notes", None) or []
        return c, notes[:-1] if notes and notes[-1] == json.loads(json.dumps(entry)) else notes

    what = f"к {form} {period or ''}".strip() if form else "общая"
    return _edit(slug, transform, f"notes: {slug} — заметка {what} ({user_label})", allowed)
