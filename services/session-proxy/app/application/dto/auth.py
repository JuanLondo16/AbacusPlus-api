from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    token: str = Field(..., description="Token de autenticación enviado al portal externo")
    pk: str = Field(
        "",
        description="Partner key del portal DIAN (ej. '10910094|1125638394'). Si no se envía, se usa EXTERNAL_FIXED_PK del entorno.",
    )
    rk: str = Field(
        "",
        description="Representative key del portal DIAN (ej. '901031352'). Si no se envía, se usa EXTERNAL_FIXED_RK del entorno.",
    )


class LoginResponse(BaseModel):
    session_id: str
    message: str = "Session created successfully"
