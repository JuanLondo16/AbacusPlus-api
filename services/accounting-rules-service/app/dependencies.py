import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.config.auth_dependency import get_tenant_db
from app.infrastructure.ai.ollama_service import OllamaEmbeddingService
from app.infrastructure.persistence.repositories.rule_repository import RuleRepository
from app.infrastructure.persistence.repositories.match_attempt_repository import MatchAttemptRepository
from app.application.use_cases.lookup_rules import LookupRulesUseCase
from app.application.use_cases.record_approved_entry import RecordApprovedEntryUseCase
from app.application.use_cases.compute_rule_stats import ComputeRuleStatsUseCase


def get_embedding_service() -> OllamaEmbeddingService:
    host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    return OllamaEmbeddingService(host=host, model=model)


def get_rule_repository(db: Session = Depends(get_tenant_db)) -> RuleRepository:
    return RuleRepository(db)


def get_match_attempt_repository(db: Session = Depends(get_tenant_db)) -> MatchAttemptRepository:
    return MatchAttemptRepository(db)


def get_lookup_rules_use_case(
    db: Session = Depends(get_tenant_db),
    embedding_service: OllamaEmbeddingService = Depends(get_embedding_service),
) -> LookupRulesUseCase:
    return LookupRulesUseCase(
        rule_repo=RuleRepository(db),
        attempt_repo=MatchAttemptRepository(db),
        embedding_service=embedding_service,
    )


def get_record_approved_entry_use_case(
    db: Session = Depends(get_tenant_db),
    embedding_service: OllamaEmbeddingService = Depends(get_embedding_service),
) -> RecordApprovedEntryUseCase:
    return RecordApprovedEntryUseCase(
        rule_repo=RuleRepository(db),
        attempt_repo=MatchAttemptRepository(db),
        embedding_service=embedding_service,
    )


def get_compute_rule_stats_use_case(
    db: Session = Depends(get_tenant_db),
) -> ComputeRuleStatsUseCase:
    return ComputeRuleStatsUseCase(
        rule_repo=RuleRepository(db),
        attempt_repo=MatchAttemptRepository(db),
    )
