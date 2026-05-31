import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.application.dto.lookup import LookupItem, LookupRequest, LookupResponse, SuggestedEntry
from app.domain.entities.accounting_rule import AccountingRule
from app.domain.entities.rule_match_attempt import RuleMatchAttempt
from app.domain.ports.repositories import MatchAttemptRepositoryPort, RuleRepositoryPort
from app.domain.ports.services import EmbeddingServicePort
from app.domain.value_objects.confidence_score import ConfidenceScore
from app.domain.value_objects.match_level import MatchLevel

logger = logging.getLogger(__name__)

_HIT_THRESHOLD = float(os.getenv("RULES_HIT_THRESHOLD", "0.85"))
_PARTIAL_THRESHOLD = float(os.getenv("RULES_PARTIAL_THRESHOLD", "0.50"))
_DECAY_FACTOR = float(os.getenv("RULES_DECAY_MONTHLY_FACTOR", "0.995"))
_SEMANTIC_SIM_THRESHOLD = float(os.getenv("RULES_SEMANTIC_SIM_THRESHOLD", "0.75"))


def _months_since(dt: Optional[datetime]) -> float:
    if dt is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.days / 30.0


def _rule_to_suggested(rule: AccountingRule) -> SuggestedEntry:
    return SuggestedEntry(
        debit_account=rule.suggested_debit_account,
        credit_account=rule.suggested_credit_account,
        tax_accounts=rule.suggested_tax_accounts or {},
        cost_center=rule.suggested_cost_center,
    )


def _suggested_payload(entry: SuggestedEntry) -> dict:
    return {
        "debit_account": entry.debit_account,
        "credit_account": entry.credit_account,
        "tax_accounts": entry.tax_accounts,
        "cost_center": entry.cost_center,
    }


class LookupRulesUseCase:
    def __init__(
        self,
        rule_repo: RuleRepositoryPort,
        attempt_repo: MatchAttemptRepositoryPort,
        embedding_service: EmbeddingServicePort,
    ):
        self._rule_repo = rule_repo
        self._attempt_repo = attempt_repo
        self._embedding_service = embedding_service

    async def execute(self, request: LookupRequest) -> LookupResponse:
        best_rule: Optional[AccountingRule] = None
        best_confidence: float = 0.0
        best_key_type: Optional[str] = None
        best_similarity: float = 0.0

        # Cascade level 1: nit_semantic (per item embedding)
        for item in request.items:
            try:
                embedding = await self._embedding_service.embed(item.description)
                hits = self._rule_repo.search_semantic(request.issuer_nit, embedding, top_k=3)
                for h in hits:
                    if h["similarity"] < _SEMANTIC_SIM_THRESHOLD:
                        continue
                    rule = self._rule_repo.get_by_id(h["rule_id"])
                    if rule is None or not rule.is_active:
                        continue
                    months_idle = _months_since(rule.last_approved_at)
                    decayed = ConfidenceScore(rule.confidence_score).with_decay(
                        months_idle, _DECAY_FACTOR
                    )
                    effective = float(decayed)
                    if effective > best_confidence:
                        best_confidence = effective
                        best_rule = rule
                        best_key_type = "nit_semantic"
                        best_similarity = h["similarity"]
            except Exception as exc:
                logger.warning(
                    "Semantic embedding failed for item '%s': %s", item.description[:50], exc
                )

        # Cascade level 2: nit_only
        if best_confidence < _HIT_THRESHOLD:
            nit_rules = self._rule_repo.find_by_nit(request.issuer_nit)
            for rule in nit_rules:
                if not rule.is_active:
                    continue
                months_idle = _months_since(rule.last_approved_at)
                decayed = float(
                    ConfidenceScore(rule.confidence_score).with_decay(months_idle, _DECAY_FACTOR)
                )
                if decayed > best_confidence:
                    best_confidence = decayed
                    best_rule = rule
                    best_key_type = "nit_only"

        # Cascade level 3: keyword_only
        if best_confidence < _HIT_THRESHOLD:
            keywords = _extract_keywords(request.items)
            if keywords:
                kw_rules = self._rule_repo.search_by_keywords(keywords, top_k=3)
                for rule in kw_rules:
                    if not rule.is_active:
                        continue
                    months_idle = _months_since(rule.last_approved_at)
                    decayed = float(
                        ConfidenceScore(rule.confidence_score).with_decay(
                            months_idle, _DECAY_FACTOR
                        )
                    )
                    if decayed > best_confidence:
                        best_confidence = decayed
                        best_rule = rule
                        best_key_type = "keyword_only"

        match_level = ConfidenceScore(best_confidence).classify(_HIT_THRESHOLD, _PARTIAL_THRESHOLD)
        suggested = (
            _rule_to_suggested(best_rule) if best_rule and match_level != MatchLevel.MISS else None
        )
        known_fields = _resolve_known_fields(best_rule, match_level)

        explanation = _build_explanation(
            match_level, best_rule, best_key_type, best_confidence, best_similarity
        )

        # Record attempt
        if request.document_id is not None:
            try:
                payload = _suggested_payload(suggested) if suggested else {}
                attempt = RuleMatchAttempt(
                    document_id=request.document_id,
                    rule_id=best_rule.id if best_rule else None,
                    match_level=match_level.value,
                    match_key_type=best_key_type,
                    confidence_at_match=best_confidence,
                    llm_used_context=match_level != MatchLevel.MISS,
                    suggested_payload=payload,
                )
                self._attempt_repo.create(attempt)
            except Exception as exc:
                logger.warning(
                    "Could not persist match attempt for doc=%s: %s", request.document_id, exc
                )

        return LookupResponse(
            match_level=match_level,
            confidence=round(best_confidence, 4),
            suggested_entry=suggested,
            known_fields=known_fields,
            explanation=explanation,
            rule_id=best_rule.id if best_rule else None,
            match_key_type=best_key_type,
        )


def _extract_keywords(items: list[LookupItem]) -> list[str]:
    stop = {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
        "o",
        "en",
        "por",
        "para",
        "con",
        "a",
        "un",
        "una",
    }
    words = []
    for item in items:
        for w in item.description.lower().split():
            w = w.strip(".,;:()\"'")
            if len(w) >= 4 and w not in stop:
                words.append(w)
    return list(set(words))[:20]


def _resolve_known_fields(rule: Optional[AccountingRule], level: MatchLevel) -> list[str]:
    if rule is None or level == MatchLevel.MISS:
        return []
    fields = ["debit_account", "credit_account"]
    if rule.suggested_tax_accounts:
        fields.append("tax_accounts")
    if rule.suggested_cost_center:
        fields.append("cost_center")
    return fields


def _build_explanation(
    level: MatchLevel,
    rule: Optional[AccountingRule],
    key_type: Optional[str],
    confidence: float,
    similarity: float,
) -> str:
    if level == MatchLevel.MISS:
        return "MISS: sin historial suficiente para este proveedor/concepto."
    if rule is None:
        return "MISS: sin regla encontrada."
    sim_info = f", similitud={similarity:.2f}" if key_type == "nit_semantic" else ""
    return (
        f"{level.value} por {key_type}{sim_info}. "
        f"Regla id={rule.id}, {rule.approval_count} aprobaciones previas, "
        f"confianza={confidence:.2f}."
    )
