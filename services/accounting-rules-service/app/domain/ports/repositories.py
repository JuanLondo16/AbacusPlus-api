import builtins
from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt


class RuleRepositoryPort(ABC):
    @abstractmethod
    def create(self, rule: AccountingRule) -> AccountingRule: ...

    @abstractmethod
    def get_by_id(self, rule_id: int) -> Optional[AccountingRule]: ...

    @abstractmethod
    def list(
        self,
        nit: Optional[str] = None,
        match_key_type: Optional[str] = None,
        min_confidence: Optional[float] = None,
        is_active: Optional[bool] = None,
    ) -> list[AccountingRule]: ...

    @abstractmethod
    def update(self, rule: AccountingRule) -> AccountingRule: ...

    @abstractmethod
    def find_by_nit(self, nit: str) -> builtins.list[AccountingRule]:
        """Return active nit_only rules for this NIT, ordered by confidence desc."""
        ...

    @abstractmethod
    def search_semantic(
        self, nit: str, embedding: builtins.list[float], top_k: int = 5
    ) -> builtins.list[dict]:
        """Cosine similarity search filtered by NIT. Returns dicts with rule_id + similarity."""
        ...

    @abstractmethod
    def search_by_keywords(
        self, keywords: builtins.list[str], top_k: int = 5
    ) -> builtins.list[AccountingRule]:
        """Return active keyword_only rules matching any of the given keywords."""
        ...


class MatchAttemptRepositoryPort(ABC):
    @abstractmethod
    def create(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt: ...

    @abstractmethod
    def get_latest_by_document(self, document_id: int) -> Optional[RuleMatchAttempt]: ...

    @abstractmethod
    def update(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt: ...

    @abstractmethod
    def stats(self) -> dict:
        """Aggregate counts: total, by match_level, final_approved breakdown."""
        ...
