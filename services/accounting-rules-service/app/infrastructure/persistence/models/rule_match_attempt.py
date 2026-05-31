from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.config.database import Base


class RuleMatchAttemptModel(Base):
    """Log de cada consulta pre-LLM al sistema de reglas."""

    __tablename__ = "rule_match_attempts"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False)
    rule_id = Column(Integer, nullable=True)  # null = MISS
    match_level = Column(String(10), nullable=False)  # HIT | PARTIAL | MISS
    match_key_type = Column(String(20), nullable=True)
    confidence_at_match = Column(Float, nullable=False, default=0.0)
    llm_used_context = Column(Boolean, nullable=False, default=False)
    final_approved = Column(Boolean, nullable=True)
    suggested_payload = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_rule_match_attempts_document_id", "document_id"),)
