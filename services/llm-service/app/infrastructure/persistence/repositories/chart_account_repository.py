from typing import Iterable, List

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


class ChartAccountRepository:
    """Read-only access to integration_chart_accounts for accounting validation."""

    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> List[dict]:
        rows = self.db.execute(
            text(
                """
                SELECT code, name, account_type, level, parent_code, accepts_movements
                FROM integration_chart_accounts
                WHERE active IS TRUE
                  AND accepts_movements IS TRUE
                ORDER BY code ASC
                """
            )
        ).mappings()
        return [dict(row) for row in rows]

    def find_active_by_codes(self, codes: Iterable[str]) -> dict[str, dict]:
        normalized_codes = sorted({str(code).strip() for code in codes if str(code).strip()})
        if not normalized_codes:
            return {}

        rows = self.db.execute(
            text(
                """
                SELECT code, name, account_type, level, parent_code, accepts_movements
                FROM integration_chart_accounts
                WHERE active IS TRUE
                  AND code IN :codes
                """
            ).bindparams(bindparam("codes", expanding=True)),
            {"codes": normalized_codes},
        ).mappings()
        return {str(row["code"]): dict(row) for row in rows}
