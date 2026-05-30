import pytest
from datetime import datetime, timezone

from app.application.dto.rule import ApprovalItem, ApprovalLine, ApprovalNotification
from app.application.use_cases.record_approved_entry import RecordApprovedEntryUseCase
from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt


def _make_use_case(rule_repo, attempt_repo, embedding_service):
    return RecordApprovedEntryUseCase(rule_repo, attempt_repo, embedding_service)


def _make_rule(rule_repo, confidence: float = 0.75) -> AccountingRule:
    rule = AccountingRule(
        match_key_type="nit_semantic",
        issuer_nit="900123456",
        suggested_debit_account="513035",
        suggested_credit_account="220501",
        suggested_tax_accounts={},
        confidence_score=confidence,
        approval_count=3,
        last_approved_at=datetime.now(timezone.utc),
    )
    return rule_repo.create(rule)


def _make_attempt(attempt_repo, rule_id: int, suggested_payload: dict, match_level: str = "HIT") -> RuleMatchAttempt:
    attempt = RuleMatchAttempt(
        document_id=10,
        rule_id=rule_id,
        match_level=match_level,
        match_key_type="nit_semantic",
        confidence_at_match=0.88,
        llm_used_context=True,
        suggested_payload=suggested_payload,
    )
    return attempt_repo.create(attempt)


def _notification(approved_debit: str = "513035", approved_credit: str = "220501") -> ApprovalNotification:
    return ApprovalNotification(
        document_id=10,
        issuer_nit="900123456",
        items=[ApprovalItem(description="Arriendo oficina", subtotal=1000000.0)],
        approved_lines=[
            ApprovalLine(cuenta=approved_debit, nombre="Gasto arriendo", debito=1000000.0, credito=0.0),
            ApprovalLine(cuenta=approved_credit, nombre="Proveedores", debito=0.0, credito=1000000.0),
        ],
    )


@pytest.mark.asyncio
async def test_approval_no_edit_reinforces_rule(rule_repo, attempt_repo, embedding_service):
    """Aprobación sin edición: score sube +0.05 y approval_count incrementa."""
    rule = _make_rule(rule_repo, confidence=0.75)
    _make_attempt(
        attempt_repo,
        rule_id=rule.id,
        suggested_payload={"debit_account": "513035", "credit_account": "220501", "tax_accounts": {}, "cost_center": None},
    )

    use_case = _make_use_case(rule_repo, attempt_repo, embedding_service)
    result = await use_case.execute(_notification())

    assert result["action"] == "reinforced"
    assert result["rule_id"] == rule.id
    updated_rule = rule_repo.get_by_id(rule.id)
    assert abs(updated_rule.confidence_score - 0.80) < 0.001
    assert updated_rule.approval_count == 4

    attempt = attempt_repo.get_latest_by_document(10)
    assert attempt.final_approved is True


@pytest.mark.asyncio
async def test_approval_with_edit_penalizes_and_creates_rule(rule_repo, attempt_repo, embedding_service):
    """Edición detectada: score baja -0.15 y se crea nueva regla con los valores correctos."""
    rule = _make_rule(rule_repo, confidence=0.75)
    _make_attempt(
        attempt_repo,
        rule_id=rule.id,
        # suggested debit era 519999 pero contador aprobó 513035
        suggested_payload={"debit_account": "519999", "credit_account": "220501", "tax_accounts": {}, "cost_center": None},
    )

    use_case = _make_use_case(rule_repo, attempt_repo, embedding_service)
    # Notificación con cuenta DIFERENTE a la sugerida
    result = await use_case.execute(_notification(approved_debit="513035"))

    assert result["action"] == "created"
    # Regla original penalizada
    original_rule = rule_repo.get_by_id(rule.id)
    assert abs(original_rule.confidence_score - 0.60) < 0.001
    assert original_rule.edit_count == 1

    attempt = attempt_repo.get_latest_by_document(10)
    assert attempt.final_approved is False

    # Nueva regla creada con cuenta correcta
    new_rule = rule_repo.get_by_id(result["rule_id"])
    assert new_rule is not None
    assert new_rule.suggested_debit_account == "513035"
    assert abs(new_rule.confidence_score - 0.60) < 0.001


@pytest.mark.asyncio
async def test_miss_creates_new_rule(rule_repo, attempt_repo, embedding_service):
    """MISS: sin attempt previo → crea nueva regla con confidence inicial 0.60."""
    # Sin attempt para el documento 99
    use_case = _make_use_case(rule_repo, attempt_repo, embedding_service)
    notification = ApprovalNotification(
        document_id=99,
        issuer_nit="555444333",
        items=[ApprovalItem(description="Servicio nuevo", subtotal=500000.0)],
        approved_lines=[
            ApprovalLine(cuenta="517010", debito=500000.0, credito=0.0),
            ApprovalLine(cuenta="220501", debito=0.0, credito=500000.0),
        ],
    )
    result = await use_case.execute(notification)

    assert result["action"] == "created"
    assert abs(result["confidence"] - 0.60) < 0.001

    new_rule = rule_repo.get_by_id(result["rule_id"])
    assert new_rule.issuer_nit == "555444333"
    assert new_rule.suggested_debit_account == "517010"
    assert new_rule.approval_count == 1


@pytest.mark.asyncio
async def test_idempotency_skips_already_processed(rule_repo, attempt_repo, embedding_service):
    """Idempotencia: segunda llamada con attempt ya final_approved=True retorna skipped."""
    rule = _make_rule(rule_repo, confidence=0.75)
    attempt = _make_attempt(
        attempt_repo,
        rule_id=rule.id,
        suggested_payload={"debit_account": "513035", "credit_account": "220501", "tax_accounts": {}, "cost_center": None},
    )
    # Marcar como ya procesado
    attempt.final_approved = True
    attempt_repo.update(attempt)

    use_case = _make_use_case(rule_repo, attempt_repo, embedding_service)
    result = await use_case.execute(_notification())

    assert result["action"] == "skipped"
