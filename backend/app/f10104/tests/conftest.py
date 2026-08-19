"""Test bootstrap for the f10104 module — mirrors app/personnel/tests/conftest.py.

test_gating imports `app.database`, so point it at in-memory SQLite: tests never
need psycopg2 or a running Postgres. `setdefault` keeps any DATABASE_URL an
environment explicitly provides.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
