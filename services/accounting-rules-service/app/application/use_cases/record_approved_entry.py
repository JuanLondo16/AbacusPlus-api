import logging
import os
from datetime import datetime, timezone

from app.application.dto.rule import ApprovalLine, ApprovalNotification
from app.domain.entities.accounting_rule import AccountingRule
from app.domain.ports.repositories import MatchAttemptRepositoryPort, RuleRepositoryPort
from app.domain.ports.services import EmbeddingServicePort
from app.domain.value_objects.confidence_score import ConfidenceScore

logger = logging.getLogger(__name__)

_INITIAL_CONFIDENCE = 0.60
_DECAY_FACTOR = float(os.getenv("RULES_DECAY_MONTHLY_FACTOR", "0.995"))


def _lines_to_payload(lines: list[ApprovalLine]) -> dict:
    """Normalize approved lines to a comparable dict."""
    return {
        "debit_account": next((l.cuenta for l in lines if l.debito > 0), ""),
        "credit_account": next((l.cuenta for l in lines if l.credito > 0), ""),
        "tax_accounts": {
            l.descripcion: l.cuenta
            for l in lines
            if l.descripcion and l.debito == 0 and l.credito == 0
        },
        "cost_center": next((l.centro_costo for l in lines if l.centro_costo), None),
    }


def _payloads_match(suggested: dict, approved: dict) -> bool:
    return suggested.get("debit_account") == approved.get("debit_account") and suggested.get(
        "credit_account"
    ) == approved.get("credit_account")


class RecordApprovedEntryUseCase:
    def __init__(
        self,
        rule_repo: RuleRepositoryPort,
        attempt_repo: MatchAttemptRepositoryPort,
        embedding_service: EmbeddingServicePort,
    ):
        self._rule_repo = rule_repo
        self._attempt_repo = attempt_repo
        self._embedding_service = embedding_service

    async def execute(self, notification: ApprovalNotification) -> dict:
        attempt = self._attempt_repo.get_latest_by_document(notification.document_id)
        approved_payload = _lines_to_payload(notification.approved_lines)
        now = datetime.now(timezone.utc)

        # Idempotency: skip if already processed
        if attempt is not None and attempt.final_approved is not None:
            logger.info("doc=%s already processed, skipping", notification.document_id)
            return {"action": "skipped", "document_id": notification.document_id}

        if attempt is not None and attempt.rule_id is not None:
            rule = self._rule_repo.get_by_id(attempt.rule_id)
            if rule is not None:
                if _payloads_match(attempt.suggested_payload, approved_payload):
                    # No edición: reforzar regla
                    updated_score = ConfidenceScore(rule.confidence_score).reinforce()
                    rule.confidence_score = float(updated_score)
                    rule.approval_count += 1
                    rule.last_approved_at = now
                    self._rule_repo.update(rule)
                    attempt.final_approved = True
                    self._attempt_repo.update(attempt)
                    logger.info("Rule %s reinforced → %.3f", rule.id, rule.confidence_score)
                    return {
                        "action": "reinforced",
                        "rule_id": rule.id,
                        "confidence": rule.confidence_score,
                    }
                else:
                    # Edición detectada: penalizar regla anterior
                    penalized = ConfidenceScore(rule.confidence_score).penalize()
                    rule.confidence_score = float(penalized)
                    rule.edit_count += 1
                    self._rule_repo.update(rule)
                    attempt.final_approved = False
                    self._attempt_repo.update(attempt)
                    logger.info(
                        "Rule %s penalized → %.3f, creating corrected rule",
                        rule.id,
                        rule.confidence_score,
                    )

        # Crear o reforzar regla con los valores aprobados (MISS o edición)
        primary_description = notification.items[0].description if notification.items else ""
        embedding = None
        try:
            if primary_description:
                embedding = await self._embedding_service.embed(primary_description)
        except Exception as exc:
            logger.warning("Embedding failed for new rule: %s", exc)

        keywords = [
            w.strip(".,;:()\"'").lower()
            for item in notification.items
            for w in item.description.split()
            if len(w) >= 4
        ][:20]

        new_rule = AccountingRule(
            match_key_type="nit_semantic" if embedding else "nit_only",
            issuer_nit=notification.issuer_nit,
            description_embedding=embedding,
            item_keywords=keywords or None,
            suggested_debit_account=approved_payload.get("debit_account", ""),
            suggested_credit_account=approved_payload.get("credit_account", ""),
            suggested_tax_accounts=approved_payload.get("tax_accounts") or {},
            suggested_cost_center=approved_payload.get("cost_center"),
            confidence_score=_INITIAL_CONFIDENCE,
            approval_count=1,
            last_approved_at=now,
        )
        created = self._rule_repo.create(new_rule)
        logger.info(
            "New rule %s created for NIT=%s, confidence=%.2f",
            created.id,
            notification.issuer_nit,
            created.confidence_score,
        )
        return {"action": "created", "rule_id": created.id, "confidence": created.confidence_score}
