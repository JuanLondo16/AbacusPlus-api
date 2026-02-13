from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, timedelta
from app.core.config import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    document_name = Column(String(255), nullable=False)
    document_number = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    hour = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False)
    document_type = Column(String(50), nullable=False)
    uuid = Column(String(255), nullable=False)
    issuer_name = Column(String(255), nullable=False)
    issuer_nit = Column(String(50), nullable=False)
    issuer_phone = Column(String(20))
    issuer_email = Column(String(255))
    receiver_name = Column(String(255), nullable=False)
    receiver_nit = Column(String(50), nullable=False)
    receiver_phone = Column(String(20))
    receiver_email = Column(String(255))
    subtotal = Column(Float, nullable=False)
    total_taxes = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    register_at = Column(DateTime, default=datetime.now(timezone.utc))
    status = Column(String(50), nullable=False)

    # Relación con DocumentDetail
    details = relationship("DocumentDetail", back_populates="document")


class DocumentDetail(Base):
    __tablename__ = "document_details"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    description = Column(String(255), nullable=False)
    concept_description_id = Column(Integer, ForeignKey("concept_descriptions.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    tax_type = Column(String(50), nullable=False)
    tax_value = Column(Float, nullable=False)
    total = Column(Float, nullable=False)

    # Relación con Document
    document = relationship("Document", back_populates="details")
    # Relación con ConceptDescription
    concept_description = relationship("ConceptDescription", back_populates="details")
    