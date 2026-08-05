"""CRUD tests.

The async endpoint handlers are called directly against a real in-memory SQLite
session (only the HTTP layer is bypassed), so no httpx/TestClient dependency is
needed. `require_service` is a route dependency, so passing `_u` explicitly skips
auth — exactly what we want for unit-level CRUD tests.
"""
import asyncio
from datetime import date
from decimal import Decimal
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
VALID_IIN = "900715312346"  # 1990-07-15, male
FAKE_USER = SimpleNamespace(id=1, full_name="Кадровик Тест", role="employee", is_active=True)


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


def _make_company(db, bin_value=VALID_BIN):
    data = s.CompanyCreate(name_ru="ТОО «Ромашка»", bin=bin_value, city="Алматы",
                           director_fio_ru="Иванов Иван Иванович")
    return run(crud.create_company(data, db=db, _u=FAKE_USER))


def _make_employee(db, iin=VALID_IIN, birth=date(1990, 7, 15), gender="male"):
    data = s.EmployeeCreate(last_name="Климов", first_name="Василий", middle_name="Александрович",
                            iin=iin, birth_date=birth, gender=gender)
    return run(crud.create_employee(data, db=db, _u=FAKE_USER))


# --- companies ---

def test_create_company_ok(db):
    company = _make_company(db)
    assert company.id is not None and company.bin == VALID_BIN


def test_create_company_invalid_bin_rejected(db):
    with pytest.raises(HTTPException) as exc:
        _make_company(db, bin_value="150640001230")  # wrong control digit
    assert exc.value.status_code == 400


# --- employees ---

def test_create_employee_invalid_iin_rejected(db):
    data = s.EmployeeCreate(last_name="Тест", first_name="Тест", iin="000000000000")
    with pytest.raises(HTTPException) as exc:
        run(crud.create_employee(data, db=db, _u=FAKE_USER))
    assert exc.value.status_code == 400


def test_create_employee_iin_dob_mismatch_warns(db):
    emp = _make_employee(db, birth=date(1991, 1, 1))  # IIN says 1990-07-15
    assert emp.warnings != []


def test_create_employee_iin_match_no_warning(db):
    emp = _make_employee(db)
    assert emp.warnings == []


def test_employee_override_persists_across_get(db):
    emp = _make_employee(db)
    upd = s.EmployeeUpdate(fio_genitive_override="Климова Василия Александровича (правка)")
    updated = run(crud.update_employee(emp.id, upd, db=db, _u=FAKE_USER))
    assert updated.fio_genitive_override == "Климова Василия Александровича (правка)"
    fetched = run(crud.get_employee(emp.id, db=db, _u=FAKE_USER))
    assert fetched.fio_genitive_override == "Климова Василия Александровича (правка)"


def test_draft_allows_empty_iin(db):
    # partial draft: empty ИИН passes (data arrives piecemeal)
    data = s.EmployeeCreate(last_name="Черновиков", first_name="Иван", iin="")
    emp = run(crud.create_employee(data, db=db, _u=FAKE_USER))
    assert emp.id is not None


# --- employments ---

def _make_employment(db, salary, rate=Decimal("1")):
    company = _make_company(db)
    employee = _make_employee(db)
    data = s.EmploymentCreate(company_id=company.id, employee_id=employee.id,
                              position_ru="менеджер", salary=salary, rate=rate)
    return run(crud.create_employment(data, db=db, _u=FAKE_USER))


def test_employment_salary_below_mzp_full_rate_warns(db):
    emp = _make_employment(db, salary=Decimal("50000"), rate=Decimal("1"))
    assert any("МЗП" in w for w in emp.warnings)


def test_employment_salary_below_mzp_part_rate_no_warn(db):
    emp = _make_employment(db, salary=Decimal("50000"), rate=Decimal("0.5"))
    assert not any("МЗП" in w for w in emp.warnings)


def test_employment_requires_existing_company_and_employee(db):
    data = s.EmploymentCreate(company_id=999, employee_id=999, position_ru="менеджер",
                              salary=Decimal("100000"))
    with pytest.raises(HTTPException) as exc:
        run(crud.create_employment(data, db=db, _u=FAKE_USER))
    assert exc.value.status_code == 404
