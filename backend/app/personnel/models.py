"""Data model for the personnel / HR-documents module (ТЗ §5).

Unlike the reconciliation module (stateless, /tmp sessions), this module
deliberately persists data: an employer is entered once, an employee card lives
long (v2 reuses it for отпуск/перевод/увольнение), and generated packages are
kept in history.

PII note: `iin` and identity-document numbers are third-party personal data of a
special risk class (ТЗ §9). They are stored as plain columns here; encrypting
them at rest is scheduled as a dedicated step (§13 step 7) and is marked with
ENCRYPT-AT-REST below so it is not forgotten.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Numeric, ForeignKey, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Company(Base):
    """Employer — a directory filled in once and reused (ТЗ §5)."""
    __tablename__ = "personnel_companies"

    id = Column(Integer, primary_key=True, index=True)
    name_ru = Column(String, nullable=False)
    name_kk = Column(String, default="")
    bin = Column(String, nullable=False, index=True)          # ENCRYPT-AT-REST (§13.7)
    legal_address = Column(String, default="")
    actual_address = Column(String, default="")

    director_fio_ru = Column(String, default="")
    director_fio_kk = Column(String, default="")
    signatory_position = Column(String, default="Директор")
    acts_on_basis = Column(String, default="Устава")         # Устав / доверенность № ...

    state_registration_date = Column(Date, nullable=True)
    bank = Column(String, default="")
    iik = Column(String, default="")
    bik = Column(String, default="")
    header_requisites = Column(Text, default="")
    logo_path = Column(String, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employments = relationship("Employment", back_populates="company")


class Employee(Base):
    """Worker card — long-lived entity (ТЗ §5, §10.4)."""
    __tablename__ = "personnel_employees"

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    middle_name = Column(String, default="")
    iin = Column(String, nullable=False, index=True)          # ENCRYPT-AT-REST (§13.7)

    document_type = Column(String, default="id_card")         # id_card | passport
    document_number = Column(String, default="")              # ENCRYPT-AT-REST (§13.7)
    document_issued_by = Column(String, default="")
    document_issue_date = Column(Date, nullable=True)

    registration_address = Column(String, default="")
    actual_address = Column(String, default="")
    phone = Column(String, default="")
    email = Column(String, default="")

    birth_date = Column(Date, nullable=True)
    gender = Column(String, default="")                       # male | female
    iban = Column(String, default="")

    citizenship = Column(String, default="Республики Казахстан")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employments = relationship("Employment", back_populates="employee")


class Employment(Base):
    """A hiring — the core of the form (ТЗ §5)."""
    __tablename__ = "personnel_employments"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("personnel_companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("personnel_employees.id", ondelete="RESTRICT"), nullable=False, index=True)

    position_ru = Column(String, nullable=False)
    position_kk = Column(String, default="")
    department = Column(String, default="")

    contract_type = Column(String, default="indefinite")      # indefinite | fixed | for_work | substitution
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)                    # for fixed-term
    probation_months = Column(Integer, default=0)             # 0..3

    salary = Column(Numeric(14, 2), default=0)
    currency = Column(String, default="KZT")
    allowances = Column(String, default="")

    hours_per_day = Column(Numeric(4, 2), nullable=True)
    hours_per_week = Column(Numeric(4, 2), nullable=True)
    work_time_from = Column(String, default="09:00")
    work_time_to = Column(String, default="18:00")
    lunch_from = Column(String, default="13:00")
    lunch_to = Column(String, default="14:00")
    vacation_days = Column(Integer, default=24)

    material_liability = Column(Boolean, default=False)       # §2 п.6 flag
    confidentiality = Column(Boolean, default=False)
    ipn_deduction = Column(String, default="base_30_mrp")     # base_30_mrp | social_882 | social_5000 | none

    # Numbering is continuous per company and year, with manual override (ТЗ §5).
    contract_number = Column(String, default="")
    order_number = Column(String, default="")
    order_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="employments")
    employee = relationship("Employee", back_populates="employments")
    packages = relationship("DocumentPackage", back_populates="employment")


class DocumentPackage(Base):
    """A generated package kept in history (ТЗ §5, §8)."""
    __tablename__ = "personnel_packages"

    id = Column(Integer, primary_key=True, index=True)
    employment_id = Column(Integer, ForeignKey("personnel_employments.id", ondelete="CASCADE"), nullable=False, index=True)
    composition = Column(Text, default="")                    # JSON: which documents were included
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    generated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    files = Column(Text, default="")                          # JSON: stored file paths
    status = Column(String, default="draft")                  # draft | issued | signed
    # So an old package re-opens in the template revision it was issued with (ТЗ §10.7).
    template_version = Column(String, default="")

    employment = relationship("Employment", back_populates="packages")


class DocumentTemplate(Base):
    """Template library, imported from Навигатор_КУ.xlsx (ТЗ §3, §5)."""
    __tablename__ = "personnel_document_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="")
    file_path = Column(String, default="")
    language = Column(String, default="ru")                   # ru | kk | ru_kk
    version = Column(String, default="1")
    status = Column(String, default="not_checked")            # actual | needs_fix | not_checked
    last_legal_review = Column(Date, nullable=True)
    comment = Column(Text, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("name", "version", name="uq_template_name_version"),)
