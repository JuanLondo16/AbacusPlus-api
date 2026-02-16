from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime
from typing import Optional


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    tenant_id: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class LoginResponse(BaseModel):
    detail: str = "Login successful"
