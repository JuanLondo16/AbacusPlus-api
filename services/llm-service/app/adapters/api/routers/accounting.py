from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.application.dto.accounting import (
    GenerateAccountingRequest,
    AccountingEntryResponse,
    DocumentWithAccountingResponse,
    SystemPromptRequest,
    SystemPromptResponse,
)
from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase
from app.application.use_cases.query_accounting import QueryAccountingUseCase
from app.infrastructure.persistence.repositories.system_prompt_repository import SystemPromptRepository
from app.dependencies import (
    get_generate_accounting_use_case,
    get_query_accounting_use_case,
    get_system_prompt_repo,
)

router = APIRouter()


@router.post(
    "/accounting/generate",
    response_model=AccountingEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generar asiento contable con LLM",
    description=(
        "Genera el asiento contable de causación (partida doble) para un documento usando OpenAI.\n\n"
        "**Flujo interno:**\n"
        "1. Obtiene el documento desde xml-processor.\n"
        "2. Recupera el system prompt activo de la BD.\n"
        "3. Consulta el RAG para obtener `top_k` facturas similares como contexto.\n"
        "4. Construye el prompt: system_prompt + contexto RAG + JSON del documento.\n"
        "5. Llama a OpenAI y parsea el JSON de respuesta.\n"
        "6. Persiste el asiento en la tabla `accounting_entries`.\n\n"
        "El asiento cumple la regla de partida doble: **total débitos = total créditos**.\n\n"
        "Si ya existe un asiento para el documento, se genera uno nuevo (no reemplaza el anterior)."
    ),
    response_description="Asiento contable generado con sus líneas de débito y crédito.",
    responses={
        404: {"description": "Documento no encontrado en xml-processor."},
        502: {"description": "Error de comunicación con OpenAI o xml-processor."},
    },
)
async def generate_accounting(
    request: GenerateAccountingRequest,
    use_case: GenerateAccountingEntryUseCase = Depends(get_generate_accounting_use_case),
):
    return await use_case.execute(request)


@router.get(
    "/accounting/entries/{document_id}",
    response_model=DocumentWithAccountingResponse,
    summary="Consultar documento con su asiento contable",
    description=(
        "Retorna el documento original completo junto con el último asiento contable "
        "generado por el LLM para ese documento.\n\n"
        "Si aún no se ha generado un asiento, el campo `accounting_entry` será `null`. "
        "En ese caso se puede disparar la generación con `POST /api/v1/accounting/generate`."
    ),
    response_description="Documento completo y asiento contable asociado (o null si no existe).",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
async def get_document_with_accounting(
    document_id: int,
    use_case: QueryAccountingUseCase = Depends(get_query_accounting_use_case),
):
    return await use_case.execute(document_id)


@router.get(
    "/accounting/system-prompts",
    response_model=List[SystemPromptResponse],
    summary="Listar system prompts disponibles",
    description=(
        "Retorna todos los system prompts almacenados en la BD. "
        "Solo uno puede estar activo a la vez (`is_active: true`). "
        "El prompt activo es el que se usa al generar asientos contables.\n\n"
        "Al arrancar el servicio se crea automáticamente el prompt por defecto "
        "**'PUC Colombia — Causación v1'** si no existe ninguno."
    ),
    response_description="Lista de system prompts con su estado de activación.",
)
def list_system_prompts(
    repo: SystemPromptRepository = Depends(get_system_prompt_repo),
):
    return repo.get_all()


@router.post(
    "/accounting/system-prompts",
    response_model=SystemPromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo system prompt",
    description=(
        "Crea un nuevo system prompt en la BD. El prompt creado queda **inactivo** por defecto. "
        "Para activarlo usar `PATCH /api/v1/accounting/system-prompts/{id}/activate`.\n\n"
        "El system prompt le indica al LLM el formato de respuesta esperado y el contexto "
        "contable (PUC, reglas de causación, etc.)."
    ),
    response_description="System prompt creado con su ID asignado.",
)
def create_system_prompt(
    request: SystemPromptRequest,
    repo: SystemPromptRepository = Depends(get_system_prompt_repo),
):
    return repo.create(name=request.name, content=request.content)


@router.patch(
    "/accounting/system-prompts/{prompt_id}/activate",
    response_model=SystemPromptResponse,
    summary="Activar un system prompt",
    description=(
        "Marca el system prompt indicado como activo y desactiva todos los demás. "
        "A partir de ese momento, todas las nuevas generaciones de asientos usarán este prompt."
    ),
    response_description="System prompt actualizado con `is_active: true`.",
    responses={
        404: {"description": "System prompt no encontrado."},
    },
)
def activate_system_prompt(
    prompt_id: int,
    repo: SystemPromptRepository = Depends(get_system_prompt_repo),
):
    prompt = repo.activate(prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt {prompt_id} not found")
    return prompt
