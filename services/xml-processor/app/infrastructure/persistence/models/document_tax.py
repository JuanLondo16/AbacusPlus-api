from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.infrastructure.config.database import Base


class DocumentTax(Base):
    __tablename__ = "document_taxes"

    id = Column(Integer, primary_key=True, index=True)
    # PostgreSQL no crea índice para las claves foráneas, y esta columna es por la que se
    # filtra SIEMPRE: al abrir un documento, al conciliar contra SIIGO y al construir el
    # payload de contabilización. `document_details.document_id` ya lo llevaba por la misma
    # razón; a esta tabla se le había pasado, así que cada lectura recorría entera una tabla
    # que crece con cada retención de cada factura.
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    tax_id = Column(Integer, nullable=False)
    # RF-02: la base gravable sobre la que se calcula la retención y el porcentaje
    # aplicado. Se muestran al usuario para su verificación antes de contabilizar.
    taxable_base = Column(Float, nullable=False, default=0.0)
    percentage = Column(Float, nullable=False, default=0.0)
    # Valor retenido = taxable_base * percentage / 100.
    value = Column(Float, nullable=False, default=0.0)
    # RF-08: origen de la retención — "llm" si nació de una sugerencia aceptada, "manual"
    # si la agregó el contador. Es el equivalente de `document_details.code_source` y sirve
    # al mismo propósito: advertir antes de regenerar sugerencias sobre trabajo manual.
    source = Column(String(10), nullable=True)

    # Relación con Document
    document = relationship("Document", back_populates="taxes")
