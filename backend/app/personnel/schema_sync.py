"""Additive schema synchronization for the personnel module.

The project intentionally has no Alembic — tables are created with
`Base.metadata.create_all`. That adds brand-new *tables* but never new *columns*
to tables that already exist on the server. This module closes that gap for the
personnel schema, in the same idempotent-startup spirit as `seed_services`.

Rules (agreed with the project owner):
  * Additive only — ADD COLUMN. Never drop, rename or retype.
  * A new column MUST be nullable or carry a server_default, otherwise the ALTER
    would fail on a non-empty table — we raise instead of guessing.
  * Every executed ALTER is logged explicitly.
  * It runs at startup, before any request is served (called from the lifespan).
  * The FIRST non-additive change is the trigger to adopt Alembic — do NOT add
    workarounds here for renames/type changes/backfills.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import Column

from app.database import Base

logger = logging.getLogger("app.personnel.schema_sync")

_PREFIX = "personnel_"


class SchemaSyncError(RuntimeError):
    """Raised when a required change is not safely additive."""


def _server_default_sql(column: Column):
    """Return the SQL text of a column's server_default, or None."""
    server_default = column.server_default
    if server_default is None:
        return None
    arg = getattr(server_default, "arg", None)
    if arg is None:
        return None
    return getattr(arg, "text", None) or str(arg)


def _column_ddl(table_name: str, column: Column, dialect) -> str:
    """Build an `ALTER TABLE ... ADD COLUMN` statement for one column.

    Raises SchemaSyncError for a NOT NULL column without a server_default (can't
    be added safely to a populated table).
    """
    coltype = column.type.compile(dialect=dialect)
    ddl = f'ALTER TABLE {table_name} ADD COLUMN "{column.name}" {coltype}'

    default_sql = _server_default_sql(column)
    if default_sql is not None:
        ddl += f" DEFAULT {default_sql}"

    if not column.nullable:
        if default_sql is None:
            raise SchemaSyncError(
                f"Нельзя аддитивно добавить NOT NULL колонку {table_name}.{column.name} "
                f"без server_default (ALTER упадёт на непустой таблице). Сделайте колонку "
                f"nullable/с server_default или переходите на Alembic."
            )
        ddl += " NOT NULL"
    return ddl


def ensure_personnel_schema(engine: Engine) -> List[str]:
    """Add any personnel_* columns declared in the models but missing in the DB.

    Returns the list of DDL statements executed (empty when already in sync).
    """
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dialect = engine.dialect
    executed: List[str] = []

    for table_name, table in Base.metadata.tables.items():
        if not table_name.startswith(_PREFIX):
            continue
        if table_name not in existing_tables:
            # Brand-new table — create_all already created it, nothing to alter.
            continue

        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            ddl = _column_ddl(table_name, column, dialect)
            logger.info("personnel schema sync: %s", ddl)
            with engine.begin() as conn:
                conn.execute(text(ddl))
            executed.append(ddl)

    if not executed:
        logger.info("personnel schema sync: изменений нет")
    return executed
