from fastapi import APIRouter, Depends, Query
from typing import List
from datetime import date

from app.application.dto.document import DocumentResponse
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase, GetDocumentByIdUseCase
from app.dependencies import get_documents_by_date_range_use_case, get_document_by_id_use_case

router = APIRouter()


@router.get(
    "/documents",
    response_model=List[DocumentResponse],
    summary="Listar documentos por rango de fechas",
    description=(
        "Retorna todos los documentos (facturas electrónicas DIAN) procesados dentro del rango "
        "de fechas indicado, incluyendo emisor, receptor, totales y líneas de detalle.\n\n"
        "Las fechas corresponden al campo `date` del documento (fecha de emisión de la factura), "
        "no a la fecha de registro en el sistema."
    ),
    response_description="Lista de documentos con sus detalles completos.",
    responses={
        400: {"description": "Parámetros de fecha inválidos."},
    },
)
async def get_documents(
    dateini: date = Query(..., description="Fecha de inicio del rango (inclusive). Formato: YYYY-MM-DD"),
    datefin: date = Query(..., description="Fecha de fin del rango (inclusive). Formato: YYYY-MM-DD"),
    use_case: GetDocumentsByDateRangeUseCase = Depends(get_documents_by_date_range_use_case),
):
    documents = use_case.execute(dateini, datefin)
    return [DocumentResponse.model_validate(doc, from_attributes=True) for doc in documents]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Obtener documento por ID",
    description=(
        "Retorna el detalle completo de un documento específico: datos del emisor, receptor, "
        "totales, impuestos y todas las líneas de detalle (conceptos facturados)."
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
