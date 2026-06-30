from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.document_tax import (
    DocumentTaxCreateRequest,
    DocumentTaxResponse,
    DocumentTaxUpdateRequest,
)
from app.dependencies import get_document_repo, get_document_tax_repo
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.document_tax_repository import (
    DocumentTaxRepository,
)

router = APIRouter()


def _ensure_document_exists(document_id: int, doc_repo: DocumentRepository) -> None:
    if doc_repo.get_by_id(document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
        )


@router.get(
    "/documents/{document_id}/taxes",
    response_model=list[DocumentTaxResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar impuestos de un documento",
    description=(
        "Retorna todos los impuestos asociados a un documento desde la tabla `document_taxes`.\n\n"
        "Cada registro relaciona el documento con un impuesto del catálogo local "
        "(`integration_taxes`) y el valor calculado para ese documento."
    ),
    response_description="Lista de impuestos del documento.",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
def list_document_taxes(
    document_id: int,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> list[DocumentTaxResponse]:
    _ensure_document_exists(document_id, doc_repo)
    return repository.list_by_document(document_id)


@router.post(
    "/documents/{document_id}/taxes",
    response_model=DocumentTaxResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear impuesto de un documento",
    description=(
        "Agrega un impuesto a un documento en la tabla `document_taxes`.\n\n"
        "`tax_id` referencia el catálogo local `integration_taxes`. "
        "`value` es el monto del impuesto para este documento."
    ),
    response_description="Impuesto del documento creado.",
    responses={
        404: {"description": "Documento no encontrado."},
    },
)
def create_document_tax(
    document_id: int,
    request: DocumentTaxCreateRequest,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> DocumentTaxResponse:
    _ensure_document_exists(document_id, doc_repo)
    return repository.create(document_id, request.tax_id, request.value)


@router.get(
    "/documents/{document_id}/taxes/{document_tax_id}",
    response_model=DocumentTaxResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener un impuesto de un documento",
    description="Retorna un registro de impuesto específico de un documento.",
    response_description="Impuesto del documento.",
    responses={
        404: {"description": "Documento o impuesto no encontrado."},
    },
)
def get_document_tax(
    document_id: int,
    document_tax_id: int,
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> DocumentTaxResponse:
    row = repository.get(document_id, document_tax_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax {document_tax_id} not found for document {document_id}",
        )
    return row


@router.patch(
    "/documents/{document_id}/taxes/{document_tax_id}",
    response_model=DocumentTaxResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar un impuesto de un documento",
    description=(
        "Actualiza `tax_id` y/o `value` de un registro de impuesto. "
        "Solo se modifican los campos presentes en el body."
    ),
    response_description="Impuesto del documento actualizado.",
    responses={
        404: {"description": "Documento o impuesto no encontrado."},
    },
)
def update_document_tax(
    document_id: int,
    document_tax_id: int,
    request: DocumentTaxUpdateRequest,
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> DocumentTaxResponse:
    row = repository.update(
        document_id, document_tax_id, tax_id=request.tax_id, value=request.value
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax {document_tax_id} not found for document {document_id}",
        )
    return row


@router.delete(
    "/documents/{document_id}/taxes/{document_tax_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un impuesto de un documento",
    description="Elimina un registro de impuesto de un documento.",
    response_description="Sin contenido.",
    responses={
        404: {"description": "Documento o impuesto no encontrado."},
    },
)
def delete_document_tax(
    document_id: int,
    document_tax_id: int,
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> None:
    if not repository.delete(document_id, document_tax_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax {document_tax_id} not found for document {document_id}",
        )
