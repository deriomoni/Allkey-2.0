"""Company CRUD tests.

Company (employer legal-entity requisites) is the only stored entity — the module
is stateless for employees' personal data. Handlers are called directly against
an in-memory SQLite session (HTTP layer bypassed); role gating is covered
separately in test_gating.py.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.users.models  # noqa: F401 — register users table (FK target)
import app.personnel.models  # noqa: F401
from app.personnel import crud
from app.personnel import schemas as s

VALID_BIN = "150640001237"
FAKE_USER = SimpleNamespace(id=1, email="t@t.kz", full_name="Кадровик", role="employee", is_active=True)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _create(db, bin_value=VALID_BIN):
    data = s.CompanyCreate(name_ru="ТОО «Ромашка»", bin=bin_value, city="Алматы",
                           director_fio_ru="Иванов Иван Иванович")
    return run(crud.create_company(data, db=db, _u=FAKE_USER))


def test_create_company_ok(db):
    company = _create(db)
    assert company.id is not None and company.bin == VALID_BIN


def test_create_company_invalid_bin_rejected(db):
    with pytest.raises(HTTPException) as exc:
        _create(db, bin_value="150640001230")  # wrong control digit
    assert exc.value.status_code == 400


def test_get_and_update_company(db):
    company = _create(db)
    updated = run(crud.update_company(company.id, s.CompanyUpdate(city="Астана"), db=db, _u=FAKE_USER))
    assert updated.city == "Астана"
    fetched = run(crud.get_company(company.id, db=db, _u=FAKE_USER))
    assert fetched.city == "Астана"


def test_get_missing_company_404(db):
    with pytest.raises(HTTPException) as exc:
        run(crud.get_company(999, db=db, _u=FAKE_USER))
    assert exc.value.status_code == 404


# --- Справочник должностей рус→каз (§4.2) ---

def test_position_translation_lookup_miss_returns_empty(db):
    res = run(crud.translate_position("менеджер по продажам", db=db, _u=FAKE_USER))
    assert res.position_kk == ""          # пары нет → пустой казахский, клиент покажет ввод


def test_position_translation_save_then_lookup(db):
    run(crud.save_position_translation(
        s.PositionTranslationIn(position_ru="менеджер по продажам", position_kk="сату жөніндегі менеджер"),
        db=db, _u=FAKE_USER))
    # регистр/лишние пробелы не мешают подбору
    res = run(crud.translate_position("  Менеджер  по   продажам ", db=db, _u=FAKE_USER))
    assert res.position_kk == "сату жөніндегі менеджер"


def test_position_translation_upsert_updates(db):
    ru = "бухгалтер"
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru=ru, position_kk="есепші"), db=db, _u=FAKE_USER))
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru=ru, position_kk="бас есепші"), db=db, _u=FAKE_USER))
    res = run(crud.translate_position(ru, db=db, _u=FAKE_USER))
    assert res.position_kk == "бас есепші"   # обновилась, не задвоилась


def test_position_translation_empty_kk_not_saved(db):
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru="кладовщик", position_kk="  "), db=db, _u=FAKE_USER))
    res = run(crud.translate_position("кладовщик", db=db, _u=FAKE_USER))
    assert res.position_kk == ""


def test_seed_positions_idempotent_and_preserves_edits(db):
    crud.seed_positions(db)
    assert run(crud.translate_position("Директор", db=db, _u=FAKE_USER)).position_kk == "Директор"
    assert run(crud.translate_position("Заместитель директора", db=db, _u=FAKE_USER)).position_kk == "Директордың орынбасары"
    # регистр/пробелы не мешают
    assert run(crud.translate_position("  генеральный   директор ", db=db, _u=FAKE_USER)).position_kk == "Бас директор"
    # пользователь поправил пару (валидный казахский) — повторный сид не затирает и не падает
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru="Директор", position_kk="Атқарушы"), db=db, _u=FAKE_USER))
    crud.seed_positions(db)
    assert run(crud.translate_position("Директор", db=db, _u=FAKE_USER)).position_kk == "Атқарушы"


def test_position_translation_rejects_garbage(db):
    # kk == ru → в справочник не пишем
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru="Логист", position_kk="Логист"), db=db, _u=FAKE_USER))
    assert run(crud.translate_position("Логист", db=db, _u=FAKE_USER)).position_kk == ""
    # kk без казахских букв → не пишем
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru="Курьер", position_kk="Курьер по городу"), db=db, _u=FAKE_USER))
    assert run(crud.translate_position("Курьер", db=db, _u=FAKE_USER)).position_kk == ""
    # настоящий казахский (есть қ/ы/…) → сохраняем
    run(crud.save_position_translation(s.PositionTranslationIn(position_ru="Снабженец", position_kk="Жабдықтаушы"), db=db, _u=FAKE_USER))
    assert run(crud.translate_position("Снабженец", db=db, _u=FAKE_USER)).position_kk == "Жабдықтаушы"


def test_kk_company_name_and_address_transforms():
    from app.personnel import kk_dictionaries as kkd
    assert kkd.kk_company_name("ТОО «Астана Консалтинг»") == "«Астана Консалтинг» ЖШС"
    assert kkd.kk_company_name("АО «Казпочта»") == "«Казпочта» АҚ"
    assert kkd.kk_company_name("ИП Оспанов") == "Оспанов ЖК"
    assert kkd.kk_company_name("Крестьянское хозяйство «Береке»") == "«Береке» Шаруа қожалығы"
    assert kkd.kk_company_name("Нечто без ОПФ") == "Нечто без ОПФ"     # не распознано — как есть
    # город из city_kz (Уральск→Орал); имя улицы — в именительный (Абая→Абай)
    assert kkd.kk_address("г. Алматы, ул. Абая, 10", "Алматы") == "Алматы қ., Абай көшесі, 10"
    assert kkd.kk_address("г. Уральск, пр. Достык, д. 5", kkd.kk_city("Уральск")).startswith("Орал қ.")
    # фамилии в родительном → именительный
    assert kkd.kk_address("ул. Жандосова, 2", "") == "Жандосов көшесі, 2"
    assert kkd.kk_address("ул. Сатпаева", "") == "Сатпаев көшесі"
    # прилагательные НЕ трогаем
    assert kkd.kk_address("ул. Северная, 5", "") == "Северная көшесі, 5"


def test_translate_company_requisites_endpoint():
    res = run(crud.translate_company_requisites(
        name="ТОО «X»", address="г. Алматы, офис 3", city="Алматы", _u=FAKE_USER))
    assert res.name_kk == "«X» ЖШС"
    assert res.address_kz == "Алматы қ., 3 кеңсе"
