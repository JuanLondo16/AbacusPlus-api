from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, timezone
from app.infrastructure.config.database import Base
from sqlalchemy.orm import relationship

class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True, index=True)
    receiver_nit = Column(String(50), nullable=False)
    concept = Column(String(255), nullable=False, default="")
    concept_code = Column(String(50), nullable=False, default="")
    account_number = Column(String(50), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    

class ConceptDescription(Base):
    __tablename__ = "concept_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    receiver_nit = Column(String(50), nullable=False)
    concept_id = Column(Integer, nullable=True, default=None)
    description = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    # Relación con DocumentDetail
    details = relationship("DocumentDetail", back_populates="concept_description")
