"""Флаги обязательств: запись решений в карточку коммитом от системы и синхронизация."""
import subprocess

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.users.models  # noqa: F401
from app.operations import obligations as obl
from app.operations import sync as sync_mod
from app.operations.config import get_ops_settings
from app.operations.models import OpsObligationFlag

CARD = """# карточка
id: acme
name: "Acme ТОО"  # комментарий сохраняется
legal_name: "Товарищество с ограниченной ответственностью \\"Acme\\""
bin: "000000000000"
tax:
  regime: general
  vat_payer: true
  forms: []   # формы

# --- Обязательства ---
obligation_flags: []

banks: []
active: true
"""
T1 = "Foo Ltd → консультации → $4 200 → п/п №118 от 14.11.2026"
T2 = "Bar GmbH → лицензия → €900 → п/п №120 от 18.11.2026"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "clients" / "acme").mkdir(parents=True)
    (tmp_path / "clients" / "acme" / "client.yaml").write_text(CARD, encoding="utf-8", newline="\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_cards.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    monkeypatch.setattr(get_ops_settings(), "arty_ops_path", str(tmp_path))
    monkeypatch.setattr(get_ops_settings(), "ops_repo_push", False)
    return tmp_path


def card(repo):
    return yaml.safe_load((repo / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8"))


def test_raise_merge_confirm_dismiss(repo):
    obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "owner@example.com")
    c = card(repo)
    f = c["obligation_flags"][0]
    assert f["status"] == "suspected" and f["source"] == "admin" and f["trigger"] == T1
    log = git(repo, "log", "-1", "--format=%an|%s").stdout
    assert log.startswith("Allkey (система)|obligations: acme")
    assert "# комментарий сохраняется" in (repo / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8")

    # тот же квартал и форма — одно основание добавляется в существующий флаг
    obl.raise_flag("acme", "101.04", "2026-Q4", [T2], "owner@example.com")
    c = card(repo)
    assert len(c["obligation_flags"]) == 1 and c["obligation_flags"][0]["trigger"] == [T1, T2]

    obl.confirm_flag("acme", 0, "101.04", "2026-Q4", "owner@example.com")
    c = card(repo)
    f = c["obligation_flags"][0]
    assert f["status"] == "confirmed" and f["decided_by"] == "owner@example.com" and f["decided_at"]
    assert c["tax"]["forms"] == [{"form": "101.04", "period": "2026-Q4", "basis": [T1, T2]}]
    assert c["tax"]["regime"] == "general" and c["banks"] == []
    assert "  forms:   # формы" in (repo / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8")

    with pytest.raises(obl.ObligationError):
        obl.confirm_flag("acme", 0, "101.04", "2026-Q4", "owner@example.com")  # уже решён

    obl.raise_flag("acme", "700.00", "2026", ["Toyota → авто → 9 800 000 ₸ → ДКП №5, 01.11.2026"], "o")
    with pytest.raises(obl.ObligationError) as e:
        obl.dismiss_flag("acme", 1, "700.00", "2026", "  ", "o")
    assert "Причина" in str(e.value)
    obl.dismiss_flag("acme", 1, "700.00", "2026", "авто клиента", "o")
    f2 = card(repo)["obligation_flags"][1]
    assert f2["status"] == "dismissed" and f2["reason"] == "авто клиента"
    assert len(card(repo)["tax"]["forms"]) == 1  # снятое в формы не попадает


def test_validation_and_races(repo):
    with pytest.raises(obl.ObligationError):
        obl.raise_flag("acme", "101.04", "2026-Q5", [T1], "o")
    with pytest.raises(obl.ObligationError):
        obl.raise_flag("acme", "101.04", "2026-Q4", ["  "], "o")
    obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "o")
    with pytest.raises(obl.ObligationError) as e:
        obl.confirm_flag("acme", 0, "300.00", "2026-Q4", "o")  # карточка изменилась
    assert e.value.status == 409
    (repo / "clients" / "acme" / "client.yaml").write_text(CARD + "# чужая правка\n", encoding="utf-8")
    with pytest.raises(obl.ObligationError) as e:
        obl.raise_flag("acme", "870.00", "2026", ["Эко → платёж → 10 000 ₸ → п/п №1, 01.11.2026"], "o")
    assert e.value.status == 409


def test_validator_rejection_restores_file(repo):
    (repo / "scripts" / "validate_cards.py").write_text("print('ОШИБКА  acme: плохо'); import sys; sys.exit(1)\n",
                                                       encoding="utf-8")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "v")
    before = (repo / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8")
    with pytest.raises(obl.ObligationError) as e:
        obl.raise_flag("acme", "101.04", "2026-Q4", [T1], "o")
    assert e.value.status == 422
    assert (repo / "clients" / "acme" / "client.yaml").read_text(encoding="utf-8") == before


def test_sync_builds_flags(repo):
    obl.raise_flag("acme", "101.04", "2026-Q4", [T1, T2], "o")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    r = sync_mod.sync_companies(db)
    assert r.ok
    rows = db.query(OpsObligationFlag).all()
    assert [(x.form, x.status, x.period, x.trigger_json) for x in rows] == [("101.04", "suspected", "2026-Q4", [T1, T2])]
    obl.confirm_flag("acme", 0, "101.04", "2026-Q4", "o")
    sync_mod.sync_one(db, "acme")
    assert db.query(OpsObligationFlag).one().status == "confirmed"
