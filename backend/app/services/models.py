from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.sql import func
from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)   # "case1", "case2", ...
    title = Column(String, nullable=False)                           # "Сверка 6010 ↔ ЭСФ"
    description = Column(String, default="")
    status = Column(String, default="production")                    # "beta" | "production"
    is_enabled = Column(Boolean, default=True)                       # глобальный выключатель
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ServiceAccess(Base):
    """Какие РОЛИ видят сервис. Одна строка = одна пара (сервис, роль)."""
    __tablename__ = "service_access"

    id = Column(Integer, primary_key=True, index=True)
    service_code = Column(String, ForeignKey("services.code", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False, index=True)                # "employee" | "client"

    __table_args__ = (UniqueConstraint("service_code", "role", name="uq_service_role"),)


class UserServiceOverride(Base):
    """Персональное правило для конкретного пользователя — сильнее роли."""
    __tablename__ = "user_service_overrides"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    service_code = Column(String, ForeignKey("services.code", ondelete="CASCADE"), nullable=False, index=True)
    allow = Column(Boolean, default=True)   # True = открыть раньше остальных, False = закрыть персонально

    __table_args__ = (UniqueConstraint("user_id", "service_code", name="uq_user_service"),)
