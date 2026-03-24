from fastapi import APIRouter, Depends, status
from typing import List
from app.application.dto.receiver import ReceiverResponse
from app.application.use_cases.query_receivers import GetAllReceiversUseCase
from app.dependencies import get_all_receivers_use_case

router = APIRouter()


@router.get("/receivers", response_model=List[ReceiverResponse], status_code=status.HTTP_200_OK)
async def get_receivers(
    use_case: GetAllReceiversUseCase = Depends(get_all_receivers_use_case),
):
    """Get the list of all receivers."""
    return use_case.execute()
