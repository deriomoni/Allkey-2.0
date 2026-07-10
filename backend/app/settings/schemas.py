from pydantic import BaseModel
from typing import Dict


class SettingsPublicResponse(BaseModel):
    whatsapp_number: str = ""
    telegram_link: str = ""
    kaspi_payment_url: str = ""


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]
