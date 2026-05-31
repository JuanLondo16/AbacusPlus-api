from datetime import datetime, timezone

import pytest
from app.application.dto.lookup import LookupItem, LookupRequest
from app.application.use_cases.lookup_rules import LookupRulesUseCase
from app.domain.entities.accounting_rule import AccountingRule
from app.domain.value_objects.match_level import MatchLevel


@pytest.fixture
def lookup_use_case(rule_repo, attempt_repo, embedding_service):
    return LookupRulesUseCase(rule_repo, attempt_repo, embedding_service)


def _make_semantic_rule(rule_repo, nit: str, confidence: float = 0.90) -> AccountingRule:
    rule = AccountingRule(
        match_key_type="nit_semantic",
        issuer_nit=nit,
        suggested_debit_account="513035",
        suggested_credit_account="220501",
        suggested_tax_accounts={"iva_descontable": "240810"},
        suggested_cost_center="CC001",
        confidence_score=confidence,
        approval_count=5,
        last_approved_at=datetime.now(timezone.utc),
    )
    rule._test_similarity = 0.92
    return rule_repo.create(rule)


def _make_nit_only_rule(rule_repo, nit: str, confidence: float = 0.75) -> AccountingRule:
    rule = AccountingRule(
        match_key_type="nit_only",
        issuer_nit=nit,
        suggested_debit_account="513540",
        suggested_credit_account="220501",
        suggested_tax_accounts={},
        confidence_score=confidence,
        approval_count=3,
        last_approved_at=datetime.now(timezone.utc),
    )
    return rule_repo.create(rule)


def _make_keyword_rule(rule_repo, confidence: float = 0.65) -> AccountingRule:
    rule = AccountingRule(
        match_key_type="keyword_only",
        item_keywords=["arriendo", "arrendamiento"],
        suggested_debit_account="513035",
        suggested_credit_account="220501",
        suggested_tax_accounts={},
        confidence_score=confidence,
    )
    return rule_repo.create(rule)


@pytest.mark.asyncio
async def test_hit_exact_semantic(rule_repo, attempt_repo, embedding_service, lookup_use_case):
    """HIT exacto: regla nit_semantic con similitud alta y confidence ≥ 0.85."""
    nit = "900123456"
    _make_semantic_rule(rule_repo, nit, confidence=0.90)

    request = LookupRequest(
        issuer_nit=nit,
        document_id=1,
        items=[LookupItem(description="Arriendo oficina mayo", subtotal=1000000.0)],
    )
    result = await lookup_use_case.execute(request)

    assert result.match_level == MatchLevel.HIT
    assert result.confidence >= 0.85
    assert result.suggested_entry is not None
    assert result.suggested_entry.debit_account == "513035"
    assert result.suggested_entry.credit_account == "220501"
    assert result.suggested_entry.cost_center == "CC001"
    assert "debit_account" in result.known_fields
    # Attempt registrado
    attempt = attempt_repo.get_latest_by_document(1)
    assert attempt is not None
    assert attempt.match_level == "HIT"
    assert attempt.llm_used_context is True


@pytest.mark.asyncio
async def test_partial_nit_only(rule_repo, attempt_repo, embedding_service):
    """PARTIAL: regla nit_only con confidence en rango [0.50, 0.84] — sin semántica."""
    # Sin regla semántica, solo nit_only con confidence 0.70
    rule_repo._rules.clear()
    nit = "888777666"
    _make_nit_only_rule(rule_repo, nit, confidence=0.70)

    use_case = LookupRulesUseCase(rule_repo, attempt_repo, embedding_service)
    request = LookupRequest(
        issuer_nit=nit,
        document_id=2,
        items=[LookupItem(description="Servicios de consultoría", subtotal=500000.0)],
    )
    result = await use_case.execute(request)

    assert result.match_level == MatchLevel.PARTIAL
    assert 0.50 <= result.confidence < 0.85
    assert result.suggested_entry is not None
    assert result.suggested_entry.debit_account == "513540"


@pytest.mark.asyncio
async def test_miss_new_provider(rule_repo, attempt_repo, embedding_service):
    """MISS: proveedor nuevo, sin reglas en ningún nivel."""
    rule_repo._rules.clear()
    use_case = LookupRulesUseCase(rule_repo, attempt_repo, embedding_service)
    request = LookupRequest(
        issuer_nit="111222333",
        document_id=3,
        items=[LookupItem(description="Producto desconocido", subtotal=50000.0)],
    )
    result = await use_case.execute(request)

    assert result.match_level == MatchLevel.MISS
    assert result.confidence < 0.50
    assert result.suggested_entry is None
    assert result.known_fields == []
    # MISS también registra attempt
    attempt = attempt_repo.get_latest_by_document(3)
    assert attempt is not None
    assert attempt.match_level == "MISS"
    assert attempt.llm_used_context is False


@pytest.mark.asyncio
async def test_keyword_only_fallback(rule_repo, attempt_repo, embedding_service):
    """keyword_only actúa como fallback cuando no hay regla por NIT."""
    rule_repo._rules.clear()
    _make_keyword_rule(rule_repo, confidence=0.65)

    use_case = LookupRulesUseCase(rule_repo, attempt_repo, embedding_service)
    request = LookupRequest(
        issuer_nit="999888777",  # NIT sin reglas
        document_id=4,
        items=[LookupItem(description="Arriendo de bodega", subtotal=200000.0)],
    )
    result = await use_case.execute(request)

    # 0.65 → PARTIAL
    assert result.match_level == MatchLevel.PARTIAL
    assert result.match_key_type == "keyword_only"
