from sqlalchemy import create_engine, inspect, text

from app.database import Base
import app.users.models  # noqa: F401
import app.operations.models  # noqa: F401
from app.operations.schema_sync import ensure_ops_schema


def test_adds_missing_legal_name_column():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE ops_companies DROP COLUMN legal_name"))
    executed = ensure_ops_schema(engine)
    assert any("legal_name" in d for d in executed)
    assert "legal_name" in {c["name"] for c in inspect(engine).get_columns("ops_companies")}
    assert ensure_ops_schema(engine) == []
