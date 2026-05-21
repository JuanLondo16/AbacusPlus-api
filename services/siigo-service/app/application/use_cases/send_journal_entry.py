from decimal import Decimal
from typing import Any, Dict, Optional

from app.application.dto.journal_entry import JournalEntryLine, SendJournalEntryRequest, SendJournalEntryResponse
from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.domain.exceptions.base import ValidationException
from app.infrastructure.siigo.siigo_client import SiigoApiClient

_JOURNAL_VOUCHERS_PATH = "/v1/journal-vouchers"


class SendJournalEntryUseCase:
    def __init__(self, credentials: ManageCredentialsUseCase):
        self.credentials = credentials

    def execute(self, request: SendJournalEntryRequest) -> SendJournalEntryResponse:
        self._validate_balance(request)

        credential = self.credentials.ensure_token(request.account_key)
        client = SiigoApiClient(credential)

        payload = self._build_payload(request)
        raw = client.post(_JOURNAL_VOUCHERS_PATH, payload)

        siigo_id = self._extract_id(raw)
        return SendJournalEntryResponse(
            status="created",
            siigo_id=siigo_id,
            siigo_response=raw,
            message="Comprobante contable creado exitosamente en SIIGO.",
        )

    def _validate_balance(self, request: SendJournalEntryRequest) -> None:
        total_debit = sum(line.debito for line in request.lines)
        total_credit = sum(line.credito for line in request.lines)
        diff = abs(total_debit - total_credit)
        if diff > Decimal("0.05"):
            raise ValidationException(
                f"Asiento no cuadra: debitos={total_debit} creditos={total_credit} diferencia={diff}"
            )

    def _build_payload(self, request: SendJournalEntryRequest) -> Dict[str, Any]:
        items = [self._build_item(line) for line in request.lines]

        payload: Dict[str, Any] = {
            "document": {"id": request.voucher_document_id},
            "date": request.entry_date.isoformat(),
            "currency": {
                "code": request.currency_code,
                "exchange_rate": float(request.exchange_rate),
            },
            "items": items,
        }

        if request.observations:
            payload["observations"] = request.observations

        return payload

    def _build_item(self, line: JournalEntryLine) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "account": {"code": line.cuenta},
            "debit": float(line.debito),
            "credit": float(line.credito),
        }

        if line.tercero:
            item["customer"] = {
                "person_type": line.tercero_tipo_persona,
                "id_type": line.tercero_tipo_id,
                "identification": line.tercero,
                "branch_code": line.tercero_sucursal,
            }

        if line.descripcion:
            item["description"] = line.descripcion

        if line.centro_costo is not None:
            item["cost_center"] = line.centro_costo

        return item

    @staticmethod
    def _extract_id(response: Dict[str, Any]) -> Optional[str]:
        for key in ("id", "voucher_id", "number", "consecutive"):
            val = response.get(key)
            if val is not None:
                return str(val)
        return None
