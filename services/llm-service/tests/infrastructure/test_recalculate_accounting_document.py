from datetime import datetime, timezone

import pytest
from app.application.dto.accounting import (
    AccountingEntryResponse,
    RecalculateAccountingDocumentRequest,
)
from app.application.use_cases.recalculate_accounting_document import (
    RecalculateAccountingDocumentUseCase,
)
from fastapi import HTTPException


class FakeDocumentClient:
    def __init__(self, document=None):
        self.document = document
        self.requested_id = None

    async def get_document(self, document_id: int):
        self.requested_id = document_id
        return self.document


class FakeGenerateAccountingUseCase:
    def __init__(self):
        self.request = None

    async def execute(self, request):
        self.request = request
        return AccountingEntryResponse(
            id=99,
            document_id=request.document_id,
            lines=[],
            model_used=request.model,
            status="generated",
            error_message=None,
            rag_context=[],
            created_at=datetime.now(timezone.utc),
        )


class TestRecalculateAccountingDocumentUseCase:
    async def test_recalculates_document_by_id(self):
        document_client = FakeDocumentClient({"id": 7, "document_number": "FE7674"})
        generate = FakeGenerateAccountingUseCase()
        use_case = RecalculateAccountingDocumentUseCase(document_client, generate)

        result = await use_case.execute(
            RecalculateAccountingDocumentRequest(
                document_id=7,
                top_k=3,
                model="gpt-4o",
            )
        )

        assert document_client.requested_id == 7
        assert generate.request.document_id == 7
        assert generate.request.top_k == 3
        assert generate.request.model == "gpt-4o"
        assert result.document_id == 7
        assert result.document_number == "FE7674"
        assert result.accounting_entry_id == 99
        assert result.status == "generated"

    async def test_raises_404_when_document_id_does_not_exist(self):
        use_case = RecalculateAccountingDocumentUseCase(
            FakeDocumentClient(None),
            FakeGenerateAccountingUseCase(),
        )

        with pytest.raises(HTTPException) as exc_info:
            await use_case.execute(RecalculateAccountingDocumentRequest(document_id=999))

        assert exc_info.value.status_code == 404
