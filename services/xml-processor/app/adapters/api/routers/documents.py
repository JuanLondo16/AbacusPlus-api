from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.dto.document import (
    AccountingEntryData,
    AccountingLineResponse,
    DocumentDetailCodeUpdateItem,
    DocumentDetailCodeUpdateResponse,
    DocumentDetailWithAccountingResponse,
    DocumentResponse,
    DocumentStatusUpdateRequest,
    DocumentSummaryResponse,
)
from app.application.use_cases.approve_document import (
    ApproveDocumentUseCase,
    UnapproveDocumentUseCase,
)
from app.application.use_cases.get_document_detail import GetDocumentDetailWithAccountingUseCase
from app.application.use_cases.query_documents import (
    GetDocumentByIdUseCase,
    GetDocumentsByDateRangeUseCase,
)
from app.dependencies import (
    get_approve_document_use_case,
    get_concept_repo,
    get_document_by_id_use_case,
    get_document_detail_use_case,
    get_document_repo,
    get_documents_by_date_range_use_case,
    get_unapprove_document_use_case,
)
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository

router = APIRouter()


def _enrich_details(doc_response: DocumentResponse, concept_repo: ConceptRepository) -> None:
    ids = [d.concept_description_id for d in doc_response.details]
    account_map = concept_repo.get_accounts_by_description_ids(ids)
    for detail in doc_response.details:
        detail.concept_account_number = account_map.get(detail.concept_description_id)


@router.get(
    "/documents",
    response_model=list[DocumentSummaryResponse],
    summary="Listar documentos por rango de fechas",
    description=(
        "Retorna un resumen de los documentos (facturas electrónicas DIAN) procesados dentro del rango "
        "de fechas indicado. Opcionalmente se puede filtrar por estado del procesamiento.\n\n"
        "Las fechas corresponden al campo `date` del documento (fecha de emisión de la factura), "
        "no a la fecha de registro en el sistema.\n\n"
        "Para obtener el detalle completo con líneas XML y asiento contable, "
        "usar `GET /api/v1/documents/{id}/full`."
    ),
    response_description="Lista de documentos con datos de resumen (sin líneas de detalle).",
    responses={
        400: {"description": "Parámetros de fecha inválidos."},
    },
)
async def get_documents(
    from_date: date = Query(
        ..., description="Fecha de inicio del rango (inclusive). Formato: YYYY-MM-DD"
    ),
    to_date: date = Query(
        ..., description="Fecha de fin del rango (inclusive). Formato: YYYY-MM-DD"
    ),
    status: Optional[int] = Query(
        None,
        description="Filtrar por código de estado. 0=Error, 100=Procesado, 200=Causado, 300=Aprobado, 400=Contabilizada.",
    ),
    use_case: GetDocumentsByDateRangeUseCase = Depends(get_documents_by_date_range_use_case),
):
    documents = use_case.execute(from_date, to_date, status)
    return [DocumentSummaryResponse.model_validate(doc, from_attributes=True) for doc in documents]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Obtener documento por ID",
    description=(
        "Retorna el detalle completo de un documento específico: datos del emisor, receptor, "
        "totales, impuestos y todas las líneas de detalle (conceptos facturados).\n\n"
        "Para obtener también el asiento contable de causación generado por el LLM, "
        "usar `GET /api/v1/documents/{id}/full`."
    ),
    response_description="Documento con todos sus campos y líneas de detalle.",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
async def get_document(
    document_id: int,
    use_case: GetDocumentByIdUseCase = Depends(get_document_by_id_use_case),
    concept_repo: ConceptRepository = Depends(get_concept_repo),
):
    doc = use_case.execute(document_id)
    response = DocumentResponse.model_validate(doc, from_attributes=True)
    _enrich_details(response, concept_repo)
    return response


@router.get(
    "/documents/{document_id}/full",
    response_model=DocumentDetailWithAccountingResponse,
    summary="Detalle completo: lectura XML + asiento contable",
    description=(
        "Retorna dos objetos combinados para un documento:\n\n"
        "- **xml_reading**: cabecera del documento y todas las líneas de detalle procesadas desde "
        "el XML DIAN (tabla `document_details`). Incluye descripción, cantidad, unidad, precio, "
        "tipo de impuesto y totales de cada concepto facturado.\n\n"
        "- **accounting**: último asiento contable de causación generado por el LLM para este "
        "documento (tablas `accounting_entries` y `accounting_entry_lines`). Incluye las cuentas "
        "PUC, valores de débito y crédito, tercero y centro de costo. Será `null` si aún no se "
        "ha generado el asiento — en ese caso usar `POST /api/v1/accounting/entries`.\n\n"
        "La obtención del asiento contable es **best-effort**: si el llm-service no está "
        "disponible, se retorna el documento con `accounting: null`."
    ),
    response_description="Objeto con xml_reading (lectura del XML) y accounting (causación contable).",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
async def get_document_detail(
    document_id: int,
    use_case: GetDocumentDetailWithAccountingUseCase = Depends(get_document_detail_use_case),
    concept_repo: ConceptRepository = Depends(get_concept_repo),
):
    try:
        result = await use_case.execute(document_id)
    except EntityNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
        )

    xml_reading = DocumentResponse.model_validate(result["document"], from_attributes=True)
    _enrich_details(xml_reading, concept_repo)

    accounting_data = result.get("accounting")
    accounting = None
    if accounting_data:
        lines = [AccountingLineResponse(**line) for line in accounting_data.get("lines", [])]
        accounting = AccountingEntryData(
            id=accounting_data["id"],
            model_used=accounting_data.get("model_used"),
            status=accounting_data["status"],
            lines=lines,
            created_at=accounting_data["created_at"],
        )

    return DocumentDetailWithAccountingResponse(xml_reading=xml_reading, accounting=accounting)


@router.patch(
    "/documents/{document_id}/approve",
    response_model=DocumentSummaryResponse,
    summary="Aprobar documento causado",
    description=(
        "Cambia el estado de un documento de `Causado` a `Aprobado`.\n\n"
        "**Requisitos:**\n"
        "- El documento debe tener un asiento contable de causación generado (estado `Causado`).\n"
        "- Si el documento no tiene asiento contable o ya está en estado `Aprobado`, "
        "la operación es rechazada.\n\n"
        "Para revertir la aprobación usar `PATCH /api/v1/documents/{id}/unapprove`."
    ),
    response_description="Documento actualizado con estado 'Aprobado'.",
    responses={
        404: {"description": "Documento no encontrado."},
        409: {"description": "El documento no está en estado 'Causado' o ya está aprobado."},
    },
)
async def approve_document(
    document_id: int,
    use_case: ApproveDocumentUseCase = Depends(get_approve_document_use_case),
    concept_repo: ConceptRepository = Depends(get_concept_repo),
):
    try:
        doc = await use_case.execute(document_id)
    except EntityNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return DocumentSummaryResponse.model_validate(doc, from_attributes=True)


@router.patch(
    "/documents/{document_id}/details",
    response_model=DocumentDetailCodeUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Asignar cuentas PUC a líneas de detalle",
    description=(
        "Actualiza los campos `code` y `type` en las líneas de detalle de un documento.\n\n"
        "Llamado por el llm-service al finalizar la asignación de cuentas PUC. "
        "También puede invocarse manualmente para corregir asignaciones.\n\n"
        "Solo se actualizan las líneas cuyos `detail_id` existan en `document_details`. "
        "Los IDs inexistentes se ignoran sin error."
    ),
    response_description="Cantidad de líneas actualizadas correctamente.",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
async def update_detail_codes(
    document_id: int,
    assignments: list[DocumentDetailCodeUpdateItem],
    doc_repo: DocumentRepository = Depends(get_document_repo),
):
    doc = doc_repo.get_by_id(document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
        )
    updated = doc_repo.update_detail_codes(
        [a.model_dump() for a in assignments]
    )
    return DocumentDetailCodeUpdateResponse(updated=updated)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentSummaryResponse,
    summary="Actualizar estado de un documento",
    description=(
        "Cambia el estado de un documento al valor indicado en `status`.\n\n"
        "**Estados destino soportados:**\n"
        "- `200` (Causado) — revierte la aprobación. El documento debe estar en estado `Aprobado`.\n\n"
        "Para aprobar un documento causado usar `PATCH /api/v1/documents/{id}/approve`."
    ),
    response_description="Documento actualizado con el nuevo estado.",
    responses={
        404: {"description": "Documento no encontrado."},
        409: {"description": "Transición de estado inválida para el estado actual del documento."},
        422: {"description": "Código de estado no soportado."},
    },
)
async def update_document_status(
    document_id: int,
    request: DocumentStatusUpdateRequest,
    use_case: UnapproveDocumentUseCase = Depends(get_unapprove_document_use_case),
    concept_repo: ConceptRepository = Depends(get_concept_repo),
):
    if request.status == 200:
        try:
            doc = use_case.execute(document_id)
        except EntityNotFoundException:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        return DocumentSummaryResponse.model_validate(doc, from_attributes=True)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Status {request.status} not supported. Supported values: 200 (Causado).",
    )
