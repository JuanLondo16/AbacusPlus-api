from fastapi import APIRouter, Depends, status

from app.application.dto.journal_entry import SendJournalEntryRequest, SendJournalEntryResponse
from app.application.use_cases.send_journal_entry import SendJournalEntryUseCase
from app.dependencies import get_send_journal_entry_use_case
from app.infrastructure.config.auth_dependency import require_write

router = APIRouter()


@router.post(
    "/siigo/journal-entries",
    dependencies=[Depends(require_write)],
    response_model=SendJournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar causacion a SIIGO",
    description=(
        "Envia un asiento contable (comprobante de causacion) al API de SIIGO Nube "
        "como un comprobante de diario (`POST /v1/journal-vouchers`).\n\n"
        "**Flujo:**\n"
        "1. Valida que debitos == creditos (tolerancia ±0.05).\n"
        "2. Renueva el token SIIGO si esta vencido.\n"
        "3. Construye el payload y llama a SIIGO.\n"
        "4. Retorna el ID del comprobante creado mas la respuesta completa de SIIGO.\n\n"
        "**Prerequisitos:**\n"
        "- Credenciales SIIGO registradas via `POST /api/v1/siigo/credentials`.\n"
        "- Token activo o credenciales validas para renovarlo automaticamente.\n"
        "- `voucher_document_id`: ID del tipo de comprobante CC en SIIGO "
        "(consultar `GET /v1/document-types?type=CC` directamente en SIIGO).\n\n"
        "**Centro de costo:** el campo `centro_costo` de cada linea debe ser el ID "
        "entero de SIIGO, no el codigo texto. Si no se tiene el ID, omitir el campo."
    ),
    response_description="Comprobante creado en SIIGO con su ID y respuesta completa.",
    responses={
        400: {"description": "Asiento no cuadra (debitos != creditos) o payload invalido."},
        401: {"description": "Credenciales SIIGO invalidas o token no renovable."},
        404: {"description": "No existe credencial activa para el account_key indicado."},
        502: {"description": "SIIGO no disponible o retorna error inesperado."},
    },
)
def send_journal_entry(
    request: SendJournalEntryRequest,
    use_case: SendJournalEntryUseCase = Depends(get_send_journal_entry_use_case),
) -> SendJournalEntryResponse:
    return use_case.execute(request)
