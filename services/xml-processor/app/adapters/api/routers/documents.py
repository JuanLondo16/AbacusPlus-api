from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List, Optional
from datetime import date

from app.application.dto.document import (
    DocumentSummaryResponse,
    DocumentResponse,
    DocumentDetailWithAccountingResponse,
    AccountingEntryData,
    AccountingLineResponse,
)
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase, GetDocumentByIdUseCase
from app.application.use_cases.get_document_detail import GetDocumentDetailWithAccountingUseCase
from app.dependencies import (
    get_documents_by_date_range_use_case,
    get_document_by_id_use_case,
    get_document_detail_use_case,
)
from app.domain.exceptions.base import EntityNotFoundException

router = APIRouter()


@router.get(
    "/documents",
    response_model=List[DocumentSummaryResponse],
    summary="Listar documentos por rango de fechas",
    description=(
        "Retorna un resumen de los documentos (facturas electrónicas DIAN) procesados dentro del rango "
        "de fechas indicado. Opcionalmente se puede filtrar por estado del procesamiento.\n\n"
        "Las fechas corresponden al campo `date` del documento (fecha de emisión de la factura), "
        "no a la fecha de registro en el sistema.\n\n"
        "Para obtener el detalle completo con líneas XML y asiento contable, "
        "usar `GET /api/v1/documents/{id}/detail`."
    ),
    response_description="Lista de documentos con datos de resumen (sin líneas de detalle).",
    responses={
        400: {"description": "Parámetros de fecha inválidos."},
    },
)
async def get_documents(
    dateini: date = Query(..., description="Fecha de inicio del rango (inclusive). Formato: YYYY-MM-DD"),
    datefin: date = Query(..., description="Fecha de fin del rango (inclusive). Formato: YYYY-MM-DD"),
    status: Optional[str] = Query(None, description="Filtrar por estado del documento. Ej: `processed`, `error`."),
    use_case: GetDocumentsByDateRangeUseCase = Depends(get_documents_by_date_range_use_case),
):
    documents = use_case.execute(dateini, datefin, status)
    return [DocumentSummaryResponse.model_validate(doc, from_attributes=True) for doc in documents]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Obtener documento por ID",
    description=(
        "Retorna el detalle completo de un documento específico: datos del emisor, receptor, "
        "totales, impuestos y todas las líneas de detalle (conceptos facturados).\n\n"
        "Para obtener también el asiento contable de causación generado por el LLM, "
        "usar `GET /api/v1/documents/{id}/detail`."
    ),
    response_description="Documento con todos sus campos y líneas de detalle.",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
async def get_document(
    document_id: int,
    use_case: GetDocumentByIdUseCase = Depends(get_document_by_id_use_case),
):
    doc = use_case.execute(document_id)
    return DocumentResponse.model_validate(doc, from_attributes=True)


@router.get(
    "/documents/{document_id}/detail",
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
        "ha generado el asiento — en ese caso usar `POST /api/v1/accounting/generate`.\n\n"
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
):
    try:
        result = await use_case.execute(document_id)
    except EntityNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")

    xml_reading = DocumentResponse.model_validate(result["document"], from_attributes=True)

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
