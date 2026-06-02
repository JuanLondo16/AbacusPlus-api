from fastapi import APIRouter, Depends, HTTPException, status

from app.application.use_cases.assign_account_codes import AssignAccountCodesUseCase
from app.dependencies import (
    get_assign_account_codes_use_case,
    get_system_prompt_repo,
)
from app.application.dto.accounting import (
    CodeAssignmentResponse,
    SystemPromptActivateRequest,
    SystemPromptRequest,
    SystemPromptResponse,
)
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

router = APIRouter()


@router.post(
    "/accounting/code-assignments/{document_id}",
    response_model=CodeAssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Asignar cuentas PUC a las líneas de un documento",
    description=(
        "Usa el LLM para asignar una cuenta PUC a cada línea de detalle del documento.\n\n"
        "**Flujo interno:**\n"
        "1. Obtiene el documento con sus líneas desde xml-processor.\n"
        "2. Obtiene el plan de cuentas (PUC) desde integration-config-service.\n"
        "3. Construye el prompt con ítems, PUC y notas del emisor.\n"
        "4. Llama a OpenAI y parsea la respuesta JSON.\n"
        "5. Valida que cada `code` exista en el PUC local.\n"
        "6. Actualiza `code` y `type` en `document_details` vía xml-processor.\n\n"
        "El proceso es **best-effort**: si el LLM falla o retorna códigos inválidos, "
        "el documento queda guardado y puede reintentarse manualmente.\n\n"
        "Este endpoint también es llamado automáticamente por xml-processor al procesar un XML."
    ),
    response_description="Cantidad de líneas asignadas, omitidas y advertencias.",
    responses={
        404: {"description": "Documento no encontrado en xml-processor."},
        502: {"description": "Error de comunicación con OpenAI o xml-processor."},
    },
)
async def assign_account_codes(
    document_id: int,
    use_case: AssignAccountCodesUseCase = Depends(get_assign_account_codes_use_case),
):
    try:
        result = await use_case.execute(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CodeAssignmentResponse(**result)


@router.get(
    "/accounting/system-prompts",
    response_model=list[SystemPromptResponse],
    summary="Listar system prompts disponibles",
    description=(
        "Retorna todos los system prompts almacenados en la BD. "
        "Solo uno puede estar activo a la vez (`is_active: true`). "
        "El prompt activo es el que usa el LLM al asignar cuentas PUC.\n\n"
        "Al arrancar el servicio se crea automáticamente el prompt por defecto "
        "si no existe ninguno."
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
        "Para activarlo usar `PATCH /api/v1/accounting/system-prompts/{id}`.\n\n"
        "El system prompt le indica al LLM el formato de respuesta esperado y el contexto "
        "contable (PUC, reglas de asignación de cuentas)."
    ),
    response_description="System prompt creado con su ID asignado.",
)
def create_system_prompt(
    request: SystemPromptRequest,
    repo: SystemPromptRepository = Depends(get_system_prompt_repo),
):
    return repo.create(name=request.name, content=request.content)


@router.patch(
    "/accounting/system-prompts/{prompt_id}",
    response_model=SystemPromptResponse,
    summary="Activar un system prompt",
    description=(
        "Marca el system prompt indicado como activo y desactiva todos los demás. "
        "A partir de ese momento todas las asignaciones de cuentas usarán este prompt."
    ),
    response_description="System prompt actualizado.",
    responses={
        404: {"description": "System prompt no encontrado."},
        422: {"description": "Solo se soporta `is_active: true`."},
    },
)
def update_system_prompt(
    prompt_id: int,
    request: SystemPromptActivateRequest,
    repo: SystemPromptRepository = Depends(get_system_prompt_repo),
):
    if not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only is_active=true is currently supported.",
        )
    prompt = repo.activate(prompt_id)
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt {prompt_id} not found"
        )
    return prompt
