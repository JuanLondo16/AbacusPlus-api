from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, UniqueConstraint, func

from app.infrastructure.config.database import Base


class Tax(Base):
    __tablename__ = "integration_taxes"
    __table_args__ = (UniqueConstraint("name", name="uq_tax_name"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    percentage = Column(Numeric(10, 4), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
