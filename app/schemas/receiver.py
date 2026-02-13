from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ReceiverBase(BaseModel):
    name: str = Field(..., max_length=255)
    nit: str = Field(..., max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    
    class Config:
        from_attributes = True
        orm_mode = True


