import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, status

from app.application.dto.journal_entry import (
    SyncRequest,
    SyncResponse,
    JournalEntryResponse,
    JournalEntryDetailResponse,
)
from app.application.use_cases.sync_journal_entries import SyncJournalEntriesUseCase
from app.application.use_cases.query_journal_entries import QueryJournalEntriesUseCase
from app.dependencies import get_sync_use_case, get_query_use_case

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/odoo/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar todos los asientos contables desde Odoo",
    description=(
        "Extrae **todos los tipos** de asientos contables en estado publicado "
        "para el rango de fechas indicado y los almacena en PostgreSQL.\n\n"
        "El campo `move_type` diferencia el tipo de documento:\n"
        "- `out_invoice` — Factura de venta\n"
        "- `out_refund` — Nota crédito de venta\n"
        "- `in_invoice` — Factura de compra\n"
        "- `in_refund` — Nota crédito de compra\n"
        "- `in_receipt` / `out_receipt` — Recibos\n"
        "- `entry` — Asiento manual\n\n"
        "La operación es **idempotente**: si un asiento ya existe (por `source_id`), "
        "se actualizan sus campos y se recrean sus líneas.\n\n"
        "Las líneas incluyen `cost_center` cuando el asiento tiene distribución analítica."
    ),
    response_description="Resumen de la sincronización: totales creados, actualizados y errores.",
    responses={
        400: {"description": "Rango de fechas inválido (date_from > date_to o mayor a 366 días)."},
        502: {"description": "No se pudo establecer conexión con Odoo."},
    },
)
def sync_journal_entries(
    request: SyncRequest,
    use_case: SyncJournalEntriesUseCase = Depends(get_sync_use_case),
) -> SyncResponse:
    return use_case.execute(request)


@router.get(
    "/odoo/entries",
    response_model=List[JournalEntryResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar asientos contables almacenados",
    description=(
        "Retorna los asientos almacenados localmente con filtros opcionales "
        "por rango de fechas, tipo de movimiento y estado.\n\n"
        "Use el parámetro `move_type` para filtrar por tipo de documento "
        "(ej. `in_invoice` para facturas de compra, `out_invoice` para ventas).\n\n"
        "No realiza ninguna llamada a Odoo; consulta únicamente la base de datos local."
    ),
    response_description="Lista de asientos contables, ordenados por fecha descendente.",
)
def list_journal_entries(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    move_type: Optional[str] = None,
    state: Optional[str] = None,
    use_case: QueryJournalEntriesUseCase = Depends(get_query_use_case),
) -> List[JournalEntryResponse]:
    return use_case.get_list(
        date_from=date_from,
        date_to=date_to,
        move_type=move_type,
        state=state,
    )


@router.get(
    "/odoo/entries/{entry_id}",
    response_model=JournalEntryDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalle de un asiento contable con sus líneas",
    description=(
        "Retorna el asiento contable indicado junto con todas sus líneas contables "
        "(cuenta, débito, crédito, tercero, centro de costo, etc.)."
    ),
    response_description="Asiento contable con el detalle de sus líneas.",
    responses={
        404: {"description": "El asiento no existe en la base de datos local."},
    },
)
def get_journal_entry(
    entry_id: int,
    use_case: QueryJournalEntriesUseCase = Depends(get_query_use_case),
) -> JournalEntryDetailResponse:
    return use_case.get_detail(entry_id)
