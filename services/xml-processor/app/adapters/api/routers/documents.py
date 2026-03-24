from fastapi import APIRouter, Depends, Query
from typing import List
from app.application.dto.document import DocumentResponse
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase, GetDocumentByIdUseCase
from app.dependencies import get_documents_by_date_range_use_case, get_document_by_id_use_case
from datetime import date

router = APIRouter()


@router.get("/documents/", response_model=List[DocumentResponse])
async def get_documents(
    dateini: date = Query(..., description="Start date"),
    datefin: date = Query(..., description="End date"),
    use_case: GetDocumentsByDateRangeUseCase = Depends(get_documents_by_date_range_use_case),
):
    """
    Get a list of documents with details within a date range.

    Args:
        dateini: Start date of the range
        datefin: End date of the range
        use_case: Injected use case
    """
    documents = use_case.execute(dateini, datefin)
    # Mapear los resultados a DocumentResponse
    return [DocumentResponse.model_validate(doc, from_attributes=True) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    use_case: GetDocumentByIdUseCase = Depends(get_document_by_id_use_case),
):
    """
    Get a specific document with its details.

    Args:
        document_id: Document ID
        use_case: Injected use case
    """
    doc = use_case.execute(document_id)
    return DocumentResponse.model_validate(doc, from_attributes=True)
