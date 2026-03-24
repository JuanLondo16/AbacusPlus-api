from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    token: str = Field(..., description="Token de autenticación enviado al portal externo")


class LoginResponse(BaseModel):
    session_id: str
    message: str = "Session created successfully"
