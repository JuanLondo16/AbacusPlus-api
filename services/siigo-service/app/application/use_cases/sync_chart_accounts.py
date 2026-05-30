import os
from typing import Any, Dict, List

from app.application.dto.chart_account import SyncChartAccountsRequest, SyncChartAccountsResponse
from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.domain.exceptions.base import ValidationException
from app.infrastructure.persistence.repositories.chart_account_repository import ChartAccountRepository
from app.infrastructure.siigo.siigo_client import SiigoApiClient


class SyncChartAccountsUseCase:
    def __init__(
        self,
        credentials: ManageCredentialsUseCase,
        repository: ChartAccountRepository,
    ):
        self.credentials = credentials
        self.repository = repository

    def execute(self, request: SyncChartAccountsRequest) -> SyncChartAccountsResponse:
        credential = self.credentials.ensure_token(account_key=request.account_key)
        path = (
            request.path
            or (credential.extra_config or {}).get("chart_accounts_path")
            or os.getenv("SIIGO_CHART_ACCOUNTS_PATH", "/v1/accounts")
        )
        if not path.startswith("/"):
            raise ValidationException("SIIGO chart accounts path must start with '/'")

        raw_accounts = SiigoApiClient(credential).get_paginated(path, page_size=request.page_size)
        accounts = [self._normalize_account(item) for item in raw_accounts]
        synced = self.repository.upsert_many(accounts)
        return SyncChartAccountsResponse(
            synced=synced,
            accounts=self.repository.list(),
        )

    @staticmethod
    def _normalize_account(item: Dict[str, Any]) -> Dict[str, Any]:
        code = item.get("code") or item.get("account") or item.get("number") or item.get("id")
        name = item.get("name") or item.get("description")
        if not code or not name:
            raise ValidationException("SIIGO account payload must include a code/id and name/description")

        return {
            "external_id": str(item.get("id")) if item.get("id") is not None else None,
            "code": str(code),
            "name": str(name),
            "account_type": item.get("type") or item.get("account_type") or item.get("classification"),
            "level": item.get("level"),
            "parent_code": item.get("parent_code") or item.get("parent"),
            "accepts_movements": item.get("accepts_movements") or item.get("accept_entries"),
            "active": item.get("active", True),
            "raw_payload": item,
        }
