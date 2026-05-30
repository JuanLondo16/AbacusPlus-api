import logging

from app.application.dto.rule import RuleStatsResponse
from app.domain.ports.repositories import MatchAttemptRepositoryPort, RuleRepositoryPort

logger = logging.getLogger(__name__)


class ComputeRuleStatsUseCase:
    def __init__(
        self,
        rule_repo: RuleRepositoryPort,
        attempt_repo: MatchAttemptRepositoryPort,
    ):
        self._rule_repo = rule_repo
        self._attempt_repo = attempt_repo

    def execute(self) -> RuleStatsResponse:
        raw = self._attempt_repo.stats()
        total = raw["total"]
        by_level = raw["by_level"]
        with_context = raw["with_context"]
        approved_no_edit = raw["approved_no_edit"]
        by_key_type = raw["by_key_type"]

        hit_count = by_level.get("HIT", 0)
        partial_count = by_level.get("PARTIAL", 0)
        miss_count = by_level.get("MISS", 0)

        hit_rate = hit_count / total if total > 0 else 0.0
        partial_rate = partial_count / total if total > 0 else 0.0
        miss_rate = miss_count / total if total > 0 else 0.0
        precision = approved_no_edit / with_context if with_context > 0 else 0.0

        total_rules = len(self._rule_repo.list(is_active=True))

        return RuleStatsResponse(
            total_attempts=total,
            hit_rate=round(hit_rate, 4),
            partial_rate=round(partial_rate, 4),
            miss_rate=round(miss_rate, 4),
            precision=round(precision, 4),
            precision_by_key_type=by_key_type,
            total_rules=total_rules,
        )
