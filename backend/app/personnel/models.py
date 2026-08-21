"""Data model for the personnel / HR-documents module.

The module is STATELESS with respect to employees' personal data (ТЗ §5): the
worker's ФИО/ИИН/оклад and the hiring conditions live only in the form state on
the client and are sent in the request body for rendering — they are never
stored on the server. This is a product decision (the service is prepared for
sale and deliberately does not collect third parties' personal data) and a
selling point stated in the offer.

What MAY be stored (not personal data of employees):
  * Company — employer legal-entity requisites (name, БИН, address, signatory)
    from the open registry; re-typing them every time would kill adoption;
  * DocumentTemplate — the template library.
A person-agnostic declension-exceptions dictionary is added separately.
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class Company(Base):
    """Employer — legal-entity requisites, entered once and reused (ТЗ §5).

    Not personal data of the client's employees: this is public-registry
    information about a legal entity, so it is kept in the DB."""
    __tablename__ = "personnel_companies"

    id = Column(Integer, primary_key=True, index=True)
    name_ru = Column(String, nullable=False)
    name_kk = Column(String, default="")
    bin = Column(String, nullable=False, index=True)
    city = Column(String, default="")                         # место издания документов
    legal_address = Column(String, default="")
    actual_address = Column(String, default="")

    address_kz = Column(String, default="")                   # kk-адрес для двуязычного ТД
    director_fio_ru = Column(String, default="")
    director_fio_kk = Column(String, default="")
    director_gender = Column(String, default="male")          # male | female — для склонения подписанта
    signatory_position = Column(String, default="Директор")
    signer_position_kz = Column(String, default="")           # kk-должность подписанта
    acts_on_basis = Column(String, default="Устава")         # Устав / доверенность № ...

    state_registration_date = Column(Date, nullable=True)
    bank = Column(String, default="")
    iik = Column(String, default="")
    bik = Column(String, default="")
    header_requisites = Column(Text, default="")
    logo_path = Column(String, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PositionTranslation(Base):
    """Справочник должностей рус→каз (§4.2). Единственное ручное казахское поле в
    форме приёма: при первом вводе должности переводчик пишет казахский вариант,
    пара сохраняется и в следующий раз подставляется автоматически. Механика та
    же, что у словаря склонений; это НЕ персональные данные — только текст должности."""
    __tablename__ = "personnel_position_translations"

    id = Column(Integer, primary_key=True, index=True)
    position_ru = Column(String, nullable=False)              # ключ (сравнение без регистра/пробелов)
    position_kk = Column(String, nullable=False, default="")

    __table_args__ = (UniqueConstraint("position_ru", name="uq_position_ru"),)


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
