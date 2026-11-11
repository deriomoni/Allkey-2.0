"""Test bootstrap для модуля «Договор с самозанятым».

Тест доступа импортирует `app.database`, поэтому направляем его на SQLite
в памяти — Postgres и psycopg2 тестам не нужны. `setdefault` не трогает
DATABASE_URL, если окружение задало свой.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
