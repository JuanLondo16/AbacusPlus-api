from fastapi import APIRouter, Depends, status

from app.application.dto.integration import AuthResponse
from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.dependencies import get_credentials_use_case

router = APIRouter()


@router.post(
    "/siigo/sessions",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticar contra SIIGO",
    description=(
        "Llama al endpoint oficial `POST /v1/auth` de SIIGO usando las credenciales "
        "guardadas localmente y persiste el `access_token` junto con su expiracion.\n\n"
        "Use este endpoint cuando cambien las credenciales o quiera forzar renovacion del token."
    ),
    response_description="Resultado de autenticacion y expiracion del token guardado.",
    responses={
        401: {"description": "SIIGO rechazo las credenciales."},
        404: {"description": "No existe credencial activa para la cuenta indicada."},
        502: {"description": "SIIGO no esta disponible o retorna error inesperado."},
    },
)
def authenticate(
    account_key: str = "default",
    use_case: ManageCredentialsUseCase = Depends(get_credentials_use_case),
) -> AuthResponse:
    return use_case.authenticate(account_key=account_key)
