from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.dto.accounting import (
    CodeAssignmentBatchItem,
    CodeAssignmentBatchRequest,
    CodeAssignmentBatchResponse,
    CodeAssignmentResponse,
    RetentionSuggestionResponse,
    SystemPromptActivateRequest,
    SystemPromptRequest,
    SystemPromptResponse,
)
from app.application.use_cases.assign_account_codes import AssignAccountCodesUseCase
from app.application.use_cases.suggest_retentions import SuggestRetentionsUseCase
from app.dependencies import (
    get_assign_account_codes_use_case,
    get_suggest_retentions_use_case,
    get_system_prompt_repo,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

router = APIRouter()


@router.post(
    "/accounting/code-assignments/{document_id}",
    dependencies=[Depends(require_write)],
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
        409: {
            "description": (
                "RF-08: no hay Plan Único de Cuentas cargado. El proceso se detiene con el "
                "mensaje «No tienes un plan único de cuenta» en lugar de dejar que el modelo "
                "sugiera cuentas de un PUC genérico."
            )
        },
        502: {"description": "Error de comunicación con OpenAI o xml-processor."},
    },
)
async def assign_account_codes(
    document_id: int,
    overwrite_manual: bool = Query(
        False,
        description=(
            "RF-04: por defecto las líneas con cuenta editada manualmente se conservan. "
            "Enviar `true` solo cuando el contador confirmó sobrescribir esas ediciones."
        ),
    ),
    use_case: AssignAccountCodesUseCase = Depends(get_assign_account_codes_use_case),
):
    try:
        result = await use_case.execute(document_id, overwrite_manual=overwrite_manual)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CodeAssignmentResponse(**result)


@router.post(
    "/accounting/code-assignments",
    dependencies=[Depends(require_write)],
    response_model=CodeAssignmentBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Asignar cuentas PUC a las líneas de varios documentos",
    description=(
        "Ejecuta la asignación de cuentas de `POST /accounting/code-assignments/{id}` sobre "
        "una selección completa de documentos, **en paralelo**.\n\n"
        "**Cuándo usarlo.** Es la vía para el botón «Calcular contabilización» sobre una "
        "selección. Recorrer los documentos llamando al endpoint individual una vez por cada "
        "uno suma la latencia del modelo tantas veces como documentos haya; en paralelo, el "
        "lote tarda aproximadamente lo que la tanda más lenta.\n\n"
        "**Concurrencia acotada.** El número de llamadas al modelo en vuelo a la vez lo fija "
        "`ASSIGN_CODES_MAX_CONCURRENCY` (5 por defecto). Es lo que impide que un lote grande "
        "se convierta en una ráfaga que el proveedor rechace con 429.\n\n"
        "**Ningún documento interrumpe el lote:** el que falle se marca con `ok: false` y su "
        "motivo en `warnings`, y los demás continúan. La única excepción es la falta de Plan "
        "Único de Cuentas, que afecta por igual a todos y responde `409`.\n\n"
        "Los ids repetidos se procesan una sola vez. Este endpoint **no cambia el estado** de "
        "los documentos: para pasarlos a `Causado` usar `PATCH /api/v1/documents` del "
        "xml-processor."
    ),
    response_description="Totales del lote y el resultado de cada documento.",
    responses={
        409: {
            "description": (
                "RF-08: no hay Plan Único de Cuentas cargado. Afecta a todo el lote, así que "
                "se responde una sola vez en lugar de repetirlo por documento."
            )
        },
        422: {"description": "Lista de documentos vacía o por encima del máximo permitido."},
    },
)
async def assign_account_codes_batch(
    request: CodeAssignmentBatchRequest,
    overwrite_manual: bool = Query(
        False,
        description=(
            "RF-04: por defecto las líneas con cuenta editada manualmente se conservan. "
            "Enviar `true` solo cuando el contador confirmó sobrescribir esas ediciones."
        ),
    ),
    use_case: AssignAccountCodesUseCase = Depends(get_assign_account_codes_use_case),
):
    resultados = await use_case.execute_many(
        request.document_ids, overwrite_manual=overwrite_manual
    )
    return CodeAssignmentBatchResponse(
        requested=len(resultados),
        succeeded=sum(1 for r in resultados if r["ok"]),
        failed=sum(1 for r in resultados if not r["ok"]),
        assigned=sum(r.get("assigned", 0) for r in resultados),
        results=[CodeAssignmentBatchItem(**r) for r in resultados],
    )


@router.post(
    "/accounting/retention-suggestions/{document_id}",
    dependencies=[Depends(require_write)],
    response_model=RetentionSuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Sugerir retenciones aplicables a un documento",
    description=(
        "RF-08: usa el LLM para determinar qué retenciones (ReteFuente, ReteICA, ReteIVA, "
        "entre otras) corresponden al tercero emisor del documento.\n\n"
        "**Flujo interno:**\n"
        "1. Obtiene el documento y el catálogo de impuestos sincronizado con SIIGO.\n"
        "2. Consulta el `tipo_contribuyente` del emisor (responsabilidades fiscales DIAN).\n"
        "3. Recupera contexto histórico del emisor vía RAG (best-effort).\n"
        "4. Pide al modelo qué retenciones aplican, limitado al catálogo entregado.\n"
        "5. Valida la respuesta contra el catálogo y calcula base y valor.\n\n"
        "**El modelo solo elige la retención.** El porcentaje se toma del catálogo y la "
        "base gravable del subtotal del documento, de modo que ningún importe tributario "
        "depende de su respuesta.\n\n"
        "**Por defecto las sugerencias no se persisten.** Se devuelven para que el contador "
        "las confirme o ajuste en la sección de retenciones; guardarlas es responsabilidad "
        "de `POST /api/v1/documents/{id}/taxes`. Las retenciones ya registradas se excluyen "
        "de la propuesta para no duplicarlas.\n\n"
        "Con `persist=true` la propuesta sí se guarda con origen `llm`. Ese es el modo que "
        "usa el procesamiento automático del XML, donde no hay interfaz esperando la "
        "respuesta y la propuesta debe quedar en el documento para que el contador la vea."
    ),
    response_description="Retenciones propuestas con su porcentaje, base y valor estimado.",
    responses={
        404: {"description": "Documento no encontrado en xml-processor."},
        409: {
            "description": (
                "El proceso se detiene por falta de un prerrequisito:\n\n"
                "- **Sin PUC cargado** → «No tienes un plan único de cuenta». RF-08 lo "
                "exige como regla de negocio crítica: sin PUC no se ejecuta "
                "contabilización con IA.\n"
                "- **Sin catálogo de impuestos sincronizado** → el modelo tendría que "
                "inventar retenciones y tarifas."
            )
        },
        502: {"description": "Error de comunicación con OpenAI o xml-processor."},
    },
)
async def suggest_retentions(
    document_id: int,
    overwrite_manual: bool = Query(
        False,
        description=(
            "RF-08: por defecto las retenciones ya registradas se excluyen de la propuesta "
            "para no duplicarlas. Enviar `true` cuando el contador confirmó reemplazar las "
            "que registró manualmente; el modelo propondrá entonces el conjunto completo."
        ),
    ),
    persist: bool = Query(
        False,
        description=(
            "RF-08: guarda la propuesta en el documento con origen `llm` en lugar de solo "
            "devolverla. Lo usa la determinación automática al procesar el XML. Es "
            "idempotente por `tax_id`: no duplica ni pisa lo que el contador ya registró."
        ),
    ),
    use_case: SuggestRetentionsUseCase = Depends(get_suggest_retentions_use_case),
):
    try:
        result = await use_case.execute(
            document_id, overwrite_manual=overwrite_manual, persist=persist
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return RetentionSuggestionResponse(**result)


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
    dependencies=[Depends(require_write)],
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
    dependencies=[Depends(require_write)],
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
