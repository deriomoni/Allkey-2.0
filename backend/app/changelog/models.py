from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy.sql import func
from app.database import Base


class ChangelogEntry(Base):
    """Запись журнала изменений сервиса (раздел «Обновления»)."""
    __tablename__ = "changelog_entries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)                      # дата изменения (не created_at)
    category = Column(String, nullable=False)               # "fix" | "feature" | "improvement"
    service_code = Column(String, nullable=True, index=True)  # "case1", "case_bank", ... или пусто
    title = Column(String, nullable=False)
    body = Column(Text, default="")
    created_by = Column(Integer, nullable=True)             # id пользователя
    created_at = Column(DateTime(timezone=True), server_default=func.now())
