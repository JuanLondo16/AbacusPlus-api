from app.application.use_cases.compute_rule_stats import ComputeRuleStatsUseCase
from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt


def _add_rule(rule_repo) -> AccountingRule:
    return rule_repo.create(
        AccountingRule(
            match_key_type="nit_only",
            issuer_nit="900000001",
            suggested_debit_account="513035",
            suggested_credit_account="220501",
            suggested_tax_accounts={},
            confidence_score=0.80,
        )
    )


def _add_attempt(
    attempt_repo, doc_id: int, level: str, key_type: str, final_approved=None
) -> RuleMatchAttempt:
    a = RuleMatchAttempt(
        document_id=doc_id,
        match_level=level,
        match_key_type=key_type,
        confidence_at_match=0.80 if level != "MISS" else 0.0,
        llm_used_context=level != "MISS",
        final_approved=final_approved,
    )
    return attempt_repo.create(a)


def test_hit_rate_and_precision_correct(rule_repo, attempt_repo):
    """hit_rate y precision se calculan correctamente."""
    _add_rule(rule_repo)
    # 4 attempts: 2 HIT (1 aprobado sin edición, 1 con edición), 1 PARTIAL, 1 MISS
    _add_attempt(attempt_repo, 1, "HIT", "nit_semantic", final_approved=True)
    _add_attempt(attempt_repo, 2, "HIT", "nit_semantic", final_approved=False)
    _add_attempt(attempt_repo, 3, "PARTIAL", "nit_only", final_approved=None)
    _add_attempt(attempt_repo, 4, "MISS", None, final_approved=None)

    use_case = ComputeRuleStatsUseCase(rule_repo, attempt_repo)
    stats = use_case.execute()

    assert stats.total_attempts == 4
    assert abs(stats.hit_rate - 0.50) < 0.001  # 2/4
    assert abs(stats.partial_rate - 0.25) < 0.001  # 1/4
    assert abs(stats.miss_rate - 0.25) < 0.001  # 1/4
    # with_context = HIT+PARTIAL = 3; approved_no_edit = 1 (solo el HIT con final_approved=True)
    assert abs(stats.precision - (1 / 3)) < 0.001
    assert stats.total_rules == 1


def test_all_miss_returns_zero_rates(rule_repo, attempt_repo):
    """Todo MISS → hit_rate=0, precision=0."""
    for i in range(3):
        _add_attempt(attempt_repo, i + 10, "MISS", None, final_approved=None)

    use_case = ComputeRuleStatsUseCase(rule_repo, attempt_repo)
    stats = use_case.execute()

    assert stats.total_attempts == 3
    assert stats.hit_rate == 0.0
    assert stats.partial_rate == 0.0
    assert stats.miss_rate == 1.0
    assert stats.precision == 0.0


def test_empty_system_returns_zeros(rule_repo, attempt_repo):
    """Sistema vacío: todo cero."""
    use_case = ComputeRuleStatsUseCase(rule_repo, attempt_repo)
    stats = use_case.execute()

    assert stats.total_attempts == 0
    assert stats.hit_rate == 0.0
    assert stats.precision == 0.0
    assert stats.total_rules == 0


def test_precision_by_key_type(rule_repo, attempt_repo):
    """precision_by_key_type refleja conteo por tipo."""
    _add_attempt(attempt_repo, 20, "HIT", "nit_semantic", final_approved=True)
    _add_attempt(attempt_repo, 21, "HIT", "nit_semantic", final_approved=True)
    _add_attempt(attempt_repo, 22, "PARTIAL", "nit_only", final_approved=None)

    use_case = ComputeRuleStatsUseCase(rule_repo, attempt_repo)
    stats = use_case.execute()

    assert stats.precision_by_key_type.get("nit_semantic") == 2
    assert stats.precision_by_key_type.get("nit_only") == 1
