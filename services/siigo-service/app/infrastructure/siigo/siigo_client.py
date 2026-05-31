import contextlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.domain.exceptions.base import SiigoAuthenticationException, SiigoConnectionException
from app.infrastructure.persistence.models.integration import IntegrationCredential


class SiigoApiClient:
    def __init__(self, credential: IntegrationCredential, timeout: float = 30.0):
        self.credential = credential
        self.base_url = credential.base_url.rstrip("/")
        self.timeout = timeout

    def authenticate(self) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/auth/access-token",
                json={
                    "username": self.credential.username,
                    "access_key": self.credential.access_key,
                },
                headers=self._base_headers(include_auth=False),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise SiigoAuthenticationException(
                f"SIIGO rejected credentials with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(f"Could not authenticate against SIIGO: {exc}") from exc

        if "access_token" not in data:
            raise SiigoAuthenticationException("SIIGO auth response did not include access_token")
        return data

    def get_paginated(self, path: str, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.get(path, params={"page": page, "page_size": page_size})
            page_results = self._extract_results(payload)
            results.extend(page_results)

            pagination = (
                payload.get("pagination") or payload.get("value", {}).get("pagination") or {}
            )
            total = int(pagination.get("total_results") or len(results))
            if not page_results or len(results) >= total:
                break
            page += 1
        return results

    def get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.get(
                url, params=params, headers=self._base_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise SiigoConnectionException(
                f"SIIGO returned status {exc.response.status_code} for {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(f"Could not call SIIGO endpoint {path}: {exc}") from exc

        if isinstance(data, list):
            return {"results": data}
        return data

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.post(
                url, json=payload, headers=self._base_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            body = ""
            with contextlib.suppress(Exception):
                body = exc.response.text
            raise SiigoConnectionException(
                f"SIIGO returned status {exc.response.status_code} for POST {path}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(
                f"Could not POST to SIIGO endpoint {path}: {exc}"
            ) from exc

    def _base_headers(self, include_auth: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.credential.partner_id:
            headers["Partner-Id"] = self.credential.partner_id
        if include_auth and self.credential.access_token:
            token_type = self.credential.token_type or "Bearer"
            headers["Authorization"] = f"{token_type} {self.credential.access_token}"
        return headers

    @staticmethod
    def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        value = payload.get("value")
        if isinstance(value, dict) and isinstance(value.get("results"), list):
            return value["results"]
        if isinstance(payload.get("results"), list):
            return payload["results"]
        return []


def token_expiration_from_response(response: dict[str, Any]) -> datetime:
    expires_in = int(response.get("expires_in") or 86400)
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)
