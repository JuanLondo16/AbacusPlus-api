import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Optional
from datetime import datetime

from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt
from app.domain.ports.repositories import RuleRepositoryPort, MatchAttemptRepositoryPort
from app.domain.ports.services import EmbeddingServicePort


class MockRuleRepository(RuleRepositoryPort):
    def __init__(self):
        self._rules: Dict[int, AccountingRule] = {}
        self._counter = 1

    def create(self, rule: AccountingRule) -> AccountingRule:
        rule.id = self._counter
        rule.created_at = datetime.utcnow()
        rule.updated_at = datetime.utcnow()
        self._rules[rule.id] = rule
        self._counter += 1
        return rule

    def get_by_id(self, rule_id: int) -> Optional[AccountingRule]:
        return self._rules.get(rule_id)

    def list(self, nit=None, match_key_type=None, min_confidence=None, is_active=None) -> List[AccountingRule]:
        result = list(self._rules.values())
        if nit is not None:
            result = [r for r in result if r.issuer_nit == nit]
        if match_key_type is not None:
            result = [r for r in result if r.match_key_type == match_key_type]
        if min_confidence is not None:
            result = [r for r in result if r.confidence_score >= min_confidence]
        if is_active is not None:
            result = [r for r in result if r.is_active == is_active]
        return sorted(result, key=lambda r: r.confidence_score, reverse=True)

    def update(self, rule: AccountingRule) -> AccountingRule:
        rule.updated_at = datetime.utcnow()
        self._rules[rule.id] = rule
        return rule

    def find_by_nit(self, nit: str) -> List[AccountingRule]:
        return [
            r for r in self._rules.values()
            if r.issuer_nit == nit and r.match_key_type == "nit_only" and r.is_active
        ]

    def search_semantic(self, nit: str, embedding: List[float], top_k: int = 5) -> List[Dict]:
        # Return all nit_semantic rules for this NIT with configurable similarity
        return [
            {"rule_id": r.id, "similarity": getattr(r, "_test_similarity", 0.9)}
            for r in self._rules.values()
            if r.issuer_nit == nit and r.match_key_type == "nit_semantic" and r.is_active
        ][:top_k]

    def search_by_keywords(self, keywords: List[str], top_k: int = 5) -> List[AccountingRule]:
        return [
            r for r in self._rules.values()
            if r.match_key_type == "keyword_only" and r.is_active
        ][:top_k]


class MockMatchAttemptRepository(MatchAttemptRepositoryPort):
    def __init__(self):
        self._attempts: Dict[int, RuleMatchAttempt] = {}
        self._by_document: Dict[int, RuleMatchAttempt] = {}
        self._counter = 1

    def create(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        attempt.id = self._counter
        attempt.created_at = datetime.utcnow()
        self._attempts[attempt.id] = attempt
        self._by_document[attempt.document_id] = attempt
        self._counter += 1
        return attempt

    def get_latest_by_document(self, document_id: int) -> Optional[RuleMatchAttempt]:
        return self._by_document.get(document_id)

    def update(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        self._attempts[attempt.id] = attempt
        self._by_document[attempt.document_id] = attempt
        return attempt

    def stats(self) -> Dict:
        all_attempts = list(self._attempts.values())
        total = len(all_attempts)
        by_level = {}
        for a in all_attempts:
            by_level[a.match_level] = by_level.get(a.match_level, 0) + 1

        with_context = sum(1 for a in all_attempts if a.match_level in ("HIT", "PARTIAL"))
        approved_no_edit = sum(
            1 for a in all_attempts
            if a.match_level in ("HIT", "PARTIAL") and a.final_approved is True
        )
        by_key_type = {}
        for a in all_attempts:
            if a.match_key_type:
                by_key_type[a.match_key_type] = by_key_type.get(a.match_key_type, 0) + 1

        return {
            "total": total,
            "by_level": by_level,
            "with_context": with_context,
            "approved_no_edit": approved_no_edit,
            "by_key_type": by_key_type,
        }


class MockEmbeddingService(EmbeddingServicePort):
    async def embed(self, text: str) -> List[float]:
        # Deterministic fake embedding based on first char
        return [float(ord(text[0]) % 10) / 10.0] * 768 if text else [0.0] * 768

    @property
    def dimensions(self) -> int:
        return 768


@pytest.fixture
def rule_repo():
    return MockRuleRepository()


@pytest.fixture
def attempt_repo():
    return MockMatchAttemptRepository()


@pytest.fixture
def embedding_service():
    return MockEmbeddingService()
