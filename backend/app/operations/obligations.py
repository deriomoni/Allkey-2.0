"""Решения по флагам обязательств: запись в client.yaml репозитория arty-ops коммитом от системы.

Карточка — источник правды. Правка текстовая: заменяется только блок `obligation_flags`
(и, при подтверждении, `tax.forms`), остальной файл и комментарии не трогаются. Перед
коммитом — проверка валидатором репозитория по этой карточке; не прошла — файл
возвращается как был. Карточку с незакоммиченными чужими правками не трогаем.

В лог — только slug-независимые счётчики и тип ошибки (раздел 1.1 ТЗ).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional

import yaml

from app.operations.config import get_ops_settings
from app.operations.sync import repo_path

logger = logging.getLogger("app.operations")

PERIOD_RE = re.compile(r"^\d{4}(-Q[1-4]|-(0[1-9]|1[0-2]))?$")
SYSTEM_AUTHOR = ("Allkey (система)", "allkey-system@users.noreply.github.com")
_lock = threading.Lock()


class ObligationError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)


def _card_path(root: Path, slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug or ""):
        raise ObligationError("Некорректный slug")
    p = root / "clients" / slug / "client.yaml"
    if not p.is_file():
        raise ObligationError("Карточка не найдена в репозитории", 404)
    return p


def _dump_list(items: list, indent: int) -> List[str]:
    if not items:
        return []
    text = yaml.safe_dump(items, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
    return [" " * indent + ln for ln in text.rstrip("\n").split("\n")]


def _replace_block(text: str, key_re: str, key_line: str, items: list, item_indent: int) -> str:
    """Заменить `key:` и его вложенные строки (с отступом > отступа ключа) новым содержимым."""
    lines = text.split("\n")
    pat = re.compile(key_re)
    start = next((i for i, ln in enumerate(lines) if pat.match(ln)), None)
    if start is None:
        raise ObligationError("В карточке нет нужного блока — обновите карточку по шаблону", 409)
    key_indent = len(lines[start]) - len(lines[start].lstrip(" "))
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        ind = len(ln) - len(ln.lstrip(" "))
        if ln.strip() and (ind > key_indent or (ind == key_indent and ln.lstrip().startswith("- "))):
            end += 1
            continue
        break
    body = _dump_list(items, item_indent)
    m = re.search(r"\s+#.*$", lines[start])  # комментарий в строке ключа сохраняем
    head = " " * key_indent + (key_line if body else key_line + " []") + (m.group(0) if m else "")
    return "\n".join(lines[:start] + [head] + body + lines[end:])


def _norm_triggers(v) -> List[str]:
    if isinstance(v, str):
        v = [v]
    out = [str(x).strip() for x in (v or []) if str(x).strip()]
    return out


def _trigger_value(tr: List[str]):
    return tr[0] if len(tr) == 1 else tr


def _run_validator(root: Path, slug: str) -> Optional[str]:
    script = root / "scripts" / "validate_cards.py"
    if not script.is_file():
        return None
    proc = subprocess.run([sys.executable, str(script), slug], cwd=str(root), capture_output=True, timeout=120,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if proc.returncode == 0:
        return None
    out = proc.stdout.decode("utf-8", "replace")
    errs = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("ОШИБКА")]
    return "; ".join(errs) or "валидатор вернул ошибку"


def _apply(slug: str, mutate, message: str) -> str:
    """Прочитать карточку, применить mutate(card)->(flags, forms|None), записать, проверить, закоммитить."""
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
        if card.get("active") is False:
            raise ObligationError("Карточка в архиве — обязательства не ведутся", 409)
        flags, forms = mutate(card)
        text = _replace_block(original, r"^obligation_flags:", "obligation_flags:", flags, 2)
        if forms is not None:
            text = _replace_block(text, r"^  forms:", "forms:", forms, 4)
        try:
            check = yaml.safe_load(text)
            assert check.get("obligation_flags", []) == flags or not flags
        except Exception:  # noqa: BLE001
            raise ObligationError("Не удалось корректно записать карточку", 500)
        path.write_text(text, encoding="utf-8", newline="\n")
        err = _run_validator(root, slug)
        if err:
            path.write_text(original, encoding="utf-8", newline="\n")
            raise ObligationError("Валидатор карточек отклонил изменение: " + err, 422)
        sha = commit_and_push(root, path, rel, original, message)
        logger.info("ops: obligation decision committed %s", sha)
        return sha


def check_branch(root: Path) -> None:
    """Решения из панели пишутся только в ветку OPS_REPO_BRANCH (на сервере — prod-decisions)."""
    want = (get_ops_settings().ops_repo_branch or "").strip()
    if not want:
        return
    cur = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if cur.returncode != 0:
        raise ObligationError("Репозиторий arty-ops недоступен (git)", 500)
    if cur.stdout.decode().strip() != want:
        raise ObligationError(f"Клон allkey-ops не на ветке {want} — решения пишутся только в неё", 409)


def commit_and_push(root: Path, path, rel, original, message: str, new_files=()) -> str:
    """Коммит от системы; при OPS_REPO_PUSH — push в origin/<OPS_REPO_BRANCH> сразу после коммита.
    path/rel/original — один файл или списки (импорт меняет несколько карточек одним коммитом);
    new_files — относительные пути новых/дописанных файлов (журнал импорта).
    Неудачный push коммит не отменяет: он уйдёт со следующим push (в лог — только sha)."""
    paths = path if isinstance(path, (list, tuple)) else [path]
    rels = list(rel) if isinstance(rel, (list, tuple)) else [rel]
    originals = original if isinstance(original, (list, tuple)) else [original]
    name, email = SYSTEM_AUTHOR
    extra = list(new_files)
    if extra:
        _git(root, "add", "--", *extra)
    commit = _git(root, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", message,
                  "--", *rels, *extra)
    if commit.returncode != 0:
        for p, o in zip(paths, originals):
            p.write_text(o, encoding="utf-8", newline="\n")
        raise ObligationError("Не удалось закоммитить карточку", 500)
    sha = _git(root, "rev-parse", "--short", "HEAD").stdout.decode().strip()
    s = get_ops_settings()
    if s.ops_repo_push:
        branch = (s.ops_repo_branch or "").strip()
        args = ["push", "-q", "origin", f"HEAD:refs/heads/{branch}"] if branch else ["push", "-q"]
        if _git(root, *args).returncode != 0:
            logger.warning("ops: commit %s not pushed", sha)
    return sha


def _today() -> dt.date:
    return dt.date.today()


def raise_flag(slug: str, form: str, period: str, trigger, user_label: str) -> str:
    form = (form or "").strip()
    period = (period or "").strip()
    tr = _norm_triggers(trigger)
    if not form or len(form) > 20:
        raise ObligationError("Укажите форму (например, 101.04)")
    if not PERIOD_RE.match(period):
        raise ObligationError("Период: ГГГГ-Qn, ГГГГ-ММ или ГГГГ (например, 2026-Q4)")
    if not tr:
        raise ObligationError("Основание обязательно: «контрагент/объект → за что → сумма → документ, дата»")

    def mutate(card):
        flags = list(card.get("obligation_flags") or [])
        for f in flags:  # открытый флаг той же формы за период — дописываем основание
            if str(f.get("form")) == form and str(f.get("period")) == period and f.get("status") in ("suspected", "confirmed"):
                cur = _norm_triggers(f.get("trigger"))
                f["trigger"] = _trigger_value(cur + [t for t in tr if t not in cur])
                return flags, _forms_with_basis(card, f) if f.get("status") == "confirmed" else None
        flags.append({
            "form": form, "status": "suspected", "period": period, "trigger": _trigger_value(tr),
            "source": "admin", "raised_at": _today(), "decided_by": None, "decided_at": None, "reason": None,
        })
        return flags, None

    return _apply(slug, mutate, f"obligations: {slug} — подозрение {form} {period} (admin {user_label})")


def _forms_with_basis(card: dict, flag: dict) -> list:
    forms = list(((card.get("tax") or {}).get("forms")) or [])
    basis = flag.get("trigger")
    forms = [x for x in forms if not (isinstance(x, dict) and str(x.get("form")) == str(flag.get("form"))
                                      and str(x.get("period")) == str(flag.get("period")))]
    forms.append({"form": str(flag.get("form")), "period": str(flag.get("period")), "basis": basis})
    return forms


def _decide(slug: str, idx: int, expect_form: str, expect_period: str, status: str, user_label: str,
            reason: Optional[str] = None) -> str:
    def mutate(card):
        flags = list(card.get("obligation_flags") or [])
        if not (0 <= idx < len(flags)):
            raise ObligationError("Флаг не найден — обновите страницу", 409)
        f = flags[idx]
        if str(f.get("form")) != expect_form or str(f.get("period")) != expect_period:
            raise ObligationError("Карточка изменилась — обновите страницу", 409)
        if f.get("status") != "suspected":
            raise ObligationError("Решение по этому флагу уже принято", 409)
        f["status"] = status
        f["decided_by"] = user_label
        f["decided_at"] = _today()
        if status == "dismissed":
            f["reason"] = reason
            return flags, None
        return flags, _forms_with_basis(card, f)

    verb = "подтверждено" if status == "confirmed" else "снято"
    return _apply(slug, mutate, f"obligations: {slug} — {expect_form} {expect_period} {verb} (admin {user_label})")


def confirm_flag(slug: str, idx: int, form: str, period: str, user_label: str) -> str:
    return _decide(slug, idx, form, period, "confirmed", user_label)


def dismiss_flag(slug: str, idx: int, form: str, period: str, reason: str, user_label: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise ObligationError("Причина снятия обязательна")
    return _decide(slug, idx, form, period, "dismissed", user_label, reason)
