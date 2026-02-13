from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.document import Document, DocumentDetail
from app.schemas.document import DocumentWithDetail
from app.core.config import get_db
from datetime import date

router = APIRouter()

@router.get("/documents/", response_model=List[DocumentWithDetail])
async def get_documents(
    db: Session = Depends(get_db),
    dateini: date = Query(..., description="Fecha inicial"),
    datefin: date = Query(..., description="Fecha final"),
):
    """
    Obtiene una lista de documentos con sus detalles.
    
    Args:
        db: Sesión de la base de datos
        dateini: Fecha inicial
        datefin: Fecha final
    Returns:
        Lista de documentos con sus detalles
    """

    if datefin < dateini:
        raise HTTPException(
            status_code=400,
            detail="La fecha final no puede ser anterior a la fecha inicial"
        )
    documents = db.query(Document).filter(Document.date >= dateini, Document.date <= datefin).all()
    return [DocumentWithDetail.from_orm(doc) for doc in documents]

@router.get("/documents/{document_id}", response_model=DocumentWithDetail)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtiene un documento específico con sus detalles.
    
    Args:
        document_id: ID del documento
        db: Sesión de la base de datos
        
    Returns:
        Documento con sus detalles
        
    Raises:
        HTTPException: Si el documento no existe
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado"
        )
    return document