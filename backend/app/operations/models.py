"""Таблицы этапа A: ops_companies, ops_company_reports, user_roles.

Миграция аддитивная, как во всём проекте: новые таблицы создаёт
`Base.metadata.create_all` при старте (Alembic в проекте нет). Типы переносимые
(JSONB/ARRAY на Postgres, JSON на SQLite в тестах).
"""
from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql import func

from app.database import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")
TextList = JSON().with_variant(ARRAY(Text()), "postgresql")


class OpsCompany(Base):
    """Карточка компании — проекция clients/<slug>/client.yaml из arty-ops."""

    __tablename__ = "ops_companies"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    bin = Column(String(12), nullable=True)
    aliases = Column(TextList, nullable=True)
    card_json = Column(JsonType, nullable=False)

    tax_regime = Column(String, nullable=True)
    vat_payer = Column(Boolean, nullable=True)

    drive_folder_name = Column(String, nullable=True)
    drive_root_folder_id = Column(String, nullable=True)
    drive_agent_folder_id = Column(String, nullable=True)

    onec_kind = Column(String, nullable=True)
    onec_url = Column(String, nullable=True)
    onec_login = Column(String, nullable=True)
    onec_note = Column(String, nullable=True)
    run_on = Column(String, nullable=True)
    closed_through = Column(Date, nullable=True)

    responsible_json = Column(JsonType, nullable=True)

    active = Column(Boolean, nullable=False, default=True)
    inactive_reason = Column(String, nullable=True)
    inactive_since = Column(Date, nullable=True)
    # Карточки из репозитория не удаляются; если папка пропала — только помечаем.
    missing_in_repo = Column(Boolean, nullable=False, default=False, server_default="false")

    synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OpsCompanyReport(Base):
    """Статус формы по компании за период."""

    __tablename__ = "ops_company_reports"
    __table_args__ = (UniqueConstraint("company_id", "form", "period", name="uq_ops_report_company_form_period"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("ops_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    form = Column(String, nullable=False)
    period = Column(String, nullable=False)
    # due | submitted | accepted | rejected | not_required
    status = Column(String, nullable=False)
    raw_value = Column(String, nullable=True)  # что было в ячейке исходного файла
    # import_xlsx | knp_watch | manual
    source = Column(String, nullable=False)
    evidence_drive_file_id = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserRoleAssignment(Base):
    """Роли модуля «Операции». Это не users.role и не лицензии."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", "company_id", name="uq_user_roles_user_role_company"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # admin | operator | keyholder | viewer | client
    role = Column(String, nullable=False)
    # admin — без company_id
    company_id = Column(Integer, ForeignKey("ops_companies.id", ondelete="CASCADE"), nullable=True)
    granted_by = Column(String, nullable=True)  # "env", "cli"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
