from pydantic import BaseModel


class CompanyLoginResponse(BaseModel):
    session_id: str
    message: str = "Login exitoso. Sesión creada."
    steps: list[str] = []
