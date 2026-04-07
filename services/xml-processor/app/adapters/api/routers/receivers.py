from fastapi import APIRouter, Depends, status
from typing import List

from app.application.dto.receiver import ReceiverResponse
from app.application.use_cases.query_receivers import GetAllReceiversUseCase
from app.dependencies import get_all_receivers_use_case

router = APIRouter()


@router.get(
    "/receivers",
    response_model=List[ReceiverResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar receptores de facturas",
    description=(
        "Retorna todos los receptores (empresas o personas que reciben facturas) "
        "registrados en el sistema. Un receptor se crea automáticamente la primera vez "
        "que aparece en una factura procesada."
    ),
    response_description="Lista de receptores con NIT, nombre y datos de contacto.",
)
async def get_receivers(
    use_case: GetAllReceiversUseCase = Depends(get_all_receivers_use_case),
):
    return use_case.execute()
