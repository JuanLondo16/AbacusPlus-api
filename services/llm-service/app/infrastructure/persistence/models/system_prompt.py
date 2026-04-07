from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.infrastructure.config.database import Base


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    content    = Column(Text, nullable=False)
    is_active  = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
