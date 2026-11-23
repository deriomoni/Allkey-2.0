"""Решения из панели: коммит в ветку prod-decisions клона и push сразу после коммита."""
import subprocess

import pytest
import yaml

from app.operations import card_edit
from app.operations import obligations as obl
from app.operations.config import get_ops_settings

CARD = """id: acme
name: "Acme ТОО"
bin: "000000000000"
tax:
  regime: general
  forms: []
obligation_flags: []
active: true
inactive_since: null
"""
T1 = "Foo Ltd → консультации → $4 200 → п/п №118 от 14.11.2026"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "arty"
    (work / "clients" / "acme").mkdir(parents=True)
    (work / "clients" / "acme" / "client.yaml").write_text(CARD, encoding="utf-8", newline="\n")
    (work / "scripts").mkdir()
    (work / "scripts" / "validate_cards.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    git(work, "init", "-q", "-b", "main")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-q", "-b", "prod-decisions")
    s = get_ops_settings()
    monkeypatch.setattr(s, "arty_ops_path", str(work))
    monkeypatch.setattr(s, "ops_repo_push", True)
    monkeypatch.setattr(s, "ops_repo_branch", "prod-decisions")
    return work, remote


def remote_log(remote, ref):
    return git(remote, "log", "--format=%an|%s", ref).stdout.strip().splitlines()


def test_decisions_pushed_to_prod_decisions(repos):
    work, remote = repos
    sha1 = obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "owner@example.com")
    sha2 = card_edit.set_hidden("acme", True, "owner@example.com")
    log = remote_log(remote, "prod-decisions")
    assert log[0].startswith("Allkey (система)|hidden: acme — скрыта")
    assert log[1].startswith("Allkey (система)|obligations: acme — подозрение 101.04 2026-Q4")
    assert git(remote, "rev-parse", "--short", "prod-decisions").stdout.strip() == sha2 != sha1
    # main на удалённом не тронут — сливает Claude Code по docs/prod-decisions.md
    assert remote_log(remote, "main") == ["t|init"]


def test_wrong_branch_refused(repos):
    work, remote = repos
    git(work, "checkout", "-q", "main")
    with pytest.raises(obl.ObligationError) as e:
        card_edit.set_hidden("acme", True, "owner@example.com")
    assert e.value.status == 409 and "prod-decisions" in str(e.value)
    assert "hidden" not in yaml.safe_load((work / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8"))
    with pytest.raises(obl.ObligationError):
        obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "owner@example.com")


def test_failed_push_keeps_commit(repos, caplog):
    work, remote = repos
    git(work, "remote", "set-url", "origin", str(work.parent / "nowhere.git"))
    sha = card_edit.set_hidden("acme", True, "owner@example.com")
    assert git(work, "rev-parse", "--short", "HEAD").stdout.strip() == sha
    assert any("not pushed" in r.getMessage() for r in caplog.records)
    # следующий успешный push уносит и прежний коммит
    git(work, "remote", "set-url", "origin", str(remote))
    obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "owner@example.com")
    assert len(remote_log(remote, "prod-decisions")) == 3
