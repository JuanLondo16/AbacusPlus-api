from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.infrastructure.config.database import Base

EMBEDDING_DIMENSIONS = 768


class AccountingRuleModel(Base):
    """Regla de causación aprendida de aprobaciones históricas."""

    __tablename__ = "accounting_rules"

    id = Column(Integer, primary_key=True, index=True)
    match_key_type = Column(String(20), nullable=False)  # nit_semantic | nit_only | keyword_only
    issuer_nit = Column(String(30), nullable=True, index=True)
    description_embedding = Column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    ciiu_code = Column(String(10), nullable=True)  # reservado
    item_keywords = Column(ARRAY(String), nullable=True)
    suggested_debit_account = Column(String(20), nullable=False)
    suggested_credit_account = Column(String(20), nullable=False)
    suggested_tax_accounts = Column(JSONB, nullable=False, default={})
    suggested_cost_center = Column(String(50), nullable=True)
    confidence_score = Column(Float, nullable=False, default=0.60)
    approval_count = Column(Integer, nullable=False, default=0)
    edit_count = Column(Integer, nullable=False, default=0)
    last_approved_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_accounting_rules_match_key_type", "match_key_type"),
        Index("ix_accounting_rules_is_active", "is_active"),
    )
