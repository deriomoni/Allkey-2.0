"""Tests for the additive schema synchronizer.

`_column_ddl` is pure (no DB): it turns a Column into an ALTER statement and
enforces the nullable-or-server_default rule. A small SQLite round-trip checks
that a genuinely missing column gets added and an already-synced table is a no-op.
"""
import pytest
from sqlalchemy import Boolean, Column, Date, Integer, MetaData, Numeric, String, Table, create_engine, inspect, text
from sqlalchemy.dialects import postgresql

from app.personnel.schema_sync import _column_ddl, ensure_personnel_schema, SchemaSyncError

PG = postgresql.dialect()


def test_nullable_string_ddl():
    ddl = _column_ddl("personnel_companies", Column("city", String()), PG)
    assert ddl == 'ALTER TABLE personnel_companies ADD COLUMN "city" VARCHAR'


def test_date_and_numeric_ddl():
    assert _column_ddl("t", Column("d", Date()), PG).endswith('"d" DATE')
    assert "NUMERIC(14, 2)" in _column_ddl("t", Column("s", Numeric(14, 2)), PG)


def test_not_null_without_default_raises():
    with pytest.raises(SchemaSyncError):
        _column_ddl("t", Column("x", String(), nullable=False), PG)


def test_not_null_with_server_default_ok():
    ddl = _column_ddl("t", Column("x", String(), nullable=False, server_default=text("'y'")), PG)
    assert "DEFAULT 'y'" in ddl and ddl.rstrip().endswith("NOT NULL")


def test_server_default_nullable():
    ddl = _column_ddl("t", Column("active", Boolean(), server_default=text("true")), PG)
    assert "DEFAULT true" in ddl and "NOT NULL" not in ddl


def test_sync_adds_missing_column_on_existing_table():
    """Simulate an old DB: create personnel_demo without the 'city' column, then
    a fuller model of the same table, and confirm the synchronizer adds 'city'."""
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # Existing (old) table, missing 'city'.
    old = MetaData()
    Table("personnel_demo", old,
          Column("id", Integer, primary_key=True),
          Column("name_ru", String))
    old.create_all(engine)

    # Declared (new) shape with the extra column, registered on the real Base.
    from app.database import Base
    demo = Table("personnel_demo", Base.metadata,
                 Column("id", Integer, primary_key=True),
                 Column("name_ru", String),
                 Column("city", String),
                 extend_existing=True)
    try:
        executed = ensure_personnel_schema(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("personnel_demo")}
        assert "city" in cols
        assert any("city" in ddl for ddl in executed)

        # Idempotent: a second run does nothing for this table.
        again = ensure_personnel_schema(engine)
        assert not any("personnel_demo" in ddl for ddl in again)
    finally:
        Base.metadata.remove(demo)  # keep the shared Base clean for other tests
