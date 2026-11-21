import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
# Тесты не должны зависеть от локального .env разработчика.
os.environ["OPS_REGISTRY_VISIBLE_TO_NON_ADMIN"] = "false"
