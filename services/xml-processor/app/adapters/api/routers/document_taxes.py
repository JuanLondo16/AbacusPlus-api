from fastapi import APIRouter, Depends, HTTPException, status

from app.adapters.api.document_guards import require_editable as _require_editable
from app.application.dto.document_tax import (
    DocumentTaxCreateRequest,
    DocumentTaxResponse,
    DocumentTaxUpdateRequest,
)
from app.dependencies import (
    get_document_repo,
    get_document_tax_repo,
    get_tax_or_retention_repo,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.document_tax_repository import (
    DocumentTaxRepository,
)
from app.infrastructure.persistence.repositories.tax_or_retention_repository import (
    TaxOrRetentionRepository,
)

router = APIRouter()


def _ensure_document_exists(document_id: int, doc_repo: DocumentRepository):
    """Comprueba que el documento exista y lo devuelve, para no volver a leerlo."""
    doc = doc_repo.get_by_id(document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found"
        )
    return doc


def _ensure_document_is_editable(document_id: int, doc_repo: DocumentRepository) -> None:
    """Existe y además admite cambios: es la puerta de toda escritura de retenciones.

    Las retenciones alteran el TOTAL A PAGAR, así que tocarlas después de aprobar cambia la
    cifra por la que el contador ya respondió. Listar no pasa por aquí: es solo lectura.
    """
    _require_editable(_ensure_document_exists(document_id, doc_repo))


def _ensure_tax_in_catalog(tax_id: int, tax_repo: TaxOrRetentionRepository):
    """El backend es la autoridad: valida que exista en el catálogo del tenant.

    `tax_id` puede apuntar a una retención (`integration_retentions`, el caso común) o a un
    impuesto del documento registrado aquí (`integration_taxes`, p. ej. Impoconsumo para
    conciliación) — `TaxOrRetentionRepository` busca en las dos. Sin esto se podían crear
    filas «huérfanas» con un tax_id inexistente (la interfaz solo ofrece opciones del
    catálogo, pero la API no lo comprobaba). Se distingue «no existe» de «existe pero está
    inactiva», igual criterio que RF-01 con el PUC y RF-07 con los centros de costo. `tax_id`
    es obligatorio en el request, así que siempre se valida.

    Devuelve el registro del catálogo: `create_document_tax` lo reutiliza para comprobar el
    tipo sin volver a consultarlo.
    """
    tax = tax_repo.get_by_id(tax_id)
    if tax is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La retención '{tax_id}' no existe en el catálogo sincronizado.",
        )
    if not tax.active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La retención '{tax.name}' está inactiva y no puede asignarse. "
                "Sincronice el catálogo o elija otra."
            ),
        )
    return tax


def _ensure_no_type_conflict(
    document_id: int,
    new_tax,
    repository: DocumentTaxRepository,
    tax_repo: TaxOrRetentionRepository,
    exclude_document_tax_id: int | None = None,
) -> None:
    """Como máximo una retención de cada tipo (RETEICA/RETEIVA/RETEFUENTE) por documento.

    RF-08 ya exige esto de las sugerencias del modelo (`_single_per_class` en
    `suggest_retentions.py`, llm-service): si el modelo propone dos tarifas del mismo tipo,
    ninguna se guarda, porque elegir entre ellas exige el concepto tributario de la
    operación, algo que no se puede inferir. Esta ruta de creación/edición manual no tenía la
    misma guarda, así que el contador podía agregar varias ReteICA (o cualquier otro tipo) con
    tarifas distintas sobre el mismo documento sin que nada lo impidiera, inflando el total
    retenido con retenciones que no deberían coexistir.

    `exclude_document_tax_id` es para la edición: al cambiar de tarifa dentro del MISMO tipo
    (p. ej. ReteICA 6,9 % → ReteICA 7 %), la fila que se está editando no debe chocar consigo
    misma — sigue guardada con su tipo viejo hasta que el repositorio confirma el cambio.
    """
    nuevo_tipo = str(new_tax.type or "").strip().lower()
    for existente in repository.list_by_document(document_id):
        if existente.id == exclude_document_tax_id:
            continue
        tax = tax_repo.get_by_id(existente.tax_id)
        if tax is not None and str(tax.type or "").strip().lower() == nuevo_tipo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"El documento ya tiene una retención de tipo '{new_tax.type}' "
                    f"(«{tax.name}»). Elimínela primero para reemplazarla."
                ),
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
    dependencies=[Depends(require_write)],
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
        409: {
            "description": (
                "El documento está aprobado o contabilizado y no admite cambios, o ya tiene "
                "una retención del mismo tipo."
            )
        },
    },
)
def create_document_tax(
    document_id: int,
    request: DocumentTaxCreateRequest,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
    tax_repo: TaxOrRetentionRepository = Depends(get_tax_or_retention_repo),
) -> DocumentTaxResponse:
    _ensure_document_is_editable(document_id, doc_repo)
    new_tax = _ensure_tax_in_catalog(request.tax_id, tax_repo)
    _ensure_no_type_conflict(document_id, new_tax, repository, tax_repo)
    return repository.create(
        document_id,
        request.tax_id,
        request.taxable_base,
        request.percentage,
        source=request.source,
    )


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
    dependencies=[Depends(require_write)],
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
        409: {
            "description": (
                "El documento está aprobado o contabilizado y no admite cambios, o el "
                "nuevo tax_id choca con otra retención del mismo tipo ya presente."
            )
        },
    },
)
def update_document_tax(
    document_id: int,
    document_tax_id: int,
    request: DocumentTaxUpdateRequest,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
    tax_repo: TaxOrRetentionRepository = Depends(get_tax_or_retention_repo),
) -> DocumentTaxResponse:
    _ensure_document_is_editable(document_id, doc_repo)
    # Solo se valida el tax_id si el update lo trae (es opcional en el body).
    if request.tax_id is not None:
        new_tax = _ensure_tax_in_catalog(request.tax_id, tax_repo)
        _ensure_no_type_conflict(
            document_id, new_tax, repository, tax_repo, exclude_document_tax_id=document_tax_id
        )
    row = repository.update(
        document_id,
        document_tax_id,
        tax_id=request.tax_id,
        taxable_base=request.taxable_base,
        percentage=request.percentage,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax {document_tax_id} not found for document {document_id}",
        )
    return row


@router.delete(
    "/documents/{document_id}/taxes/{document_tax_id}",
    dependencies=[Depends(require_write)],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un impuesto de un documento",
    description="Elimina un registro de impuesto de un documento.",
    response_description="Sin contenido.",
    responses={
        404: {"description": "Documento o impuesto no encontrado."},
        409: {"description": "El documento está aprobado o contabilizado y no admite cambios."},
    },
)
def delete_document_tax(
    document_id: int,
    document_tax_id: int,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    repository: DocumentTaxRepository = Depends(get_document_tax_repo),
) -> None:
    _ensure_document_is_editable(document_id, doc_repo)
    if not repository.delete(document_id, document_tax_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax {document_tax_id} not found for document {document_id}",
        )
