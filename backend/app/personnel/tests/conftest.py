"""Test bootstrap for the personnel module.

Some tests import `app.database` (via schema_sync). Point it at in-memory SQLite
so tests never need psycopg2 or a running Postgres. `setdefault` keeps any
DATABASE_URL an environment explicitly provides.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
