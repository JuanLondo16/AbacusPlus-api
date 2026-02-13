from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.config import get_db
from app.models.receiver import Receiver
from app.schemas.receiver import ReceiverBase
from pydantic import BaseModel

router = APIRouter()

@router.get("/receivers", response_model=List[ReceiverBase], status_code=status.HTTP_200_OK)
async def get_receivers(
    db: Session = Depends(get_db),
):
    """
    Obtiene una lista de receptores con paginación.
    
    Args:
        
        
    Returns:
        Lista de receptores
    """
    try:
        receivers = db.query(Receiver).all()
        return [ReceiverBase.from_orm(receiver) for receiver in receivers]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener receptores: {str(e)}"
        )
