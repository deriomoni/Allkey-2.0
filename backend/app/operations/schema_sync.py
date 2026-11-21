"""Аддитивная синхронизация схемы модуля «Операции» (как personnel/schema_sync.py).

create_all создаёт новые таблицы, но не добавляет колонки в существующие. Здесь —
только ADD COLUMN для ops_* и user_roles; новая колонка обязана быть nullable или
с server_default. Первое неаддитивное изменение — повод перейти на Alembic.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine

from app.database import Base
from app.personnel.schema_sync import _column_ddl

logger = logging.getLogger("app.operations")


def _ours(table_name: str) -> bool:
    return table_name.startswith("ops_") or table_name == "user_roles"


def ensure_ops_schema(engine: Engine) -> List[str]:
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())
    executed: List[str] = []
    for table_name, table in Base.metadata.tables.items():
        if not _ours(table_name) or table_name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            ddl = _column_ddl(table_name, column, engine.dialect)
            logger.info("ops schema sync: %s", ddl)
            with engine.begin() as conn:
                conn.execute(text(ddl))
            executed.append(ddl)
    return executed
