"""Настройки модуля — только из окружения/.env, без значений по умолчанию, раскрывающих данные."""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/operations/config.py → корень репозитория Allkey
_REPO_ROOT = Path(__file__).resolve().parents[3]


class OpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Путь к локальному клону arty-ops (там clients/*/client.yaml и scripts/validate_cards.py).
    arty_ops_path: str = ""
    # user_id владельца, которому при старте выдаётся роль admin модуля. Больше никому.
    ops_admin_user_id: Optional[int] = None
    # Решения по обязательствам коммитятся в клон arty-ops от имени системы; пушить ли сразу.
    # Локально — false (коммит остаётся в клоне), на сервере включает владелец.
    ops_repo_push: bool = False
    # Ветка клона allkey-ops для решений из панели (на сервере — prod-decisions). Пусто — без проверки,
    # push в текущую ветку. Порядок слияния prod-decisions → main — allkey-ops docs/prod-decisions.md.
    ops_repo_branch: str = ""
    # Собранный отдельный бандл фронта модуля (npm run build:ops).
    ops_ui_bundle_path: str = str(_REPO_ROOT / "frontend" / "dist-ops" / "ops.js")
    # API КГД «Сведения по контрагентам». Токен — только локально (backend/.env), на сервер не переносится.
    kgd_api_token: Optional[SecretStr] = None
    kgd_api_url: str = "https://kgd.gov.kz/services/isnaportal/public/get-sur-data"


@lru_cache()
def get_ops_settings() -> OpsSettings:
    return OpsSettings()
