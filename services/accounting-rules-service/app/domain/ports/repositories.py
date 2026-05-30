from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt


class RuleRepositoryPort(ABC):
    @abstractmethod
    def create(self, rule: AccountingRule) -> AccountingRule:
        ...

    @abstractmethod
    def get_by_id(self, rule_id: int) -> Optional[AccountingRule]:
        ...

    @abstractmethod
    def list(
        self,
        nit: Optional[str] = None,
        match_key_type: Optional[str] = None,
        min_confidence: Optional[float] = None,
        is_active: Optional[bool] = None,
    ) -> List[AccountingRule]:
        ...

    @abstractmethod
    def update(self, rule: AccountingRule) -> AccountingRule:
        ...

    @abstractmethod
    def find_by_nit(self, nit: str) -> List[AccountingRule]:
        """Return active nit_only rules for this NIT, ordered by confidence desc."""
        ...

    @abstractmethod
    def search_semantic(
        self, nit: str, embedding: List[float], top_k: int = 5
    ) -> List[Dict]:
        """Cosine similarity search filtered by NIT. Returns dicts with rule_id + similarity."""
        ...

    @abstractmethod
    def search_by_keywords(self, keywords: List[str], top_k: int = 5) -> List[AccountingRule]:
        """Return active keyword_only rules matching any of the given keywords."""
        ...


class MatchAttemptRepositoryPort(ABC):
    @abstractmethod
    def create(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        ...

    @abstractmethod
    def get_latest_by_document(self, document_id: int) -> Optional[RuleMatchAttempt]:
        ...

    @abstractmethod
    def update(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        ...

    @abstractmethod
    def stats(self) -> Dict:
        """Aggregate counts: total, by match_level, final_approved breakdown."""
        ...
