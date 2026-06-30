from sqlalchemy import Column, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.infrastructure.config.database import Base


class DocumentTax(Base):
    __tablename__ = "document_taxes"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    tax_id = Column(Integer, nullable=False)
    value = Column(Float, nullable=False, default=0.0)

    # Relación con Document
    document = relationship("Document", back_populates="taxes")
