import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.entities.accounting_rule import AccountingRule
from app.domain.ports.repositories import RuleRepositoryPort
from app.infrastructure.persistence.models.accounting_rule import AccountingRuleModel

logger = logging.getLogger(__name__)


def _to_entity(m: AccountingRuleModel) -> AccountingRule:
    return AccountingRule(
        id=m.id,
        match_key_type=m.match_key_type,
        issuer_nit=m.issuer_nit,
        description_embedding=None,  # never load large vector back into entity
        ciiu_code=m.ciiu_code,
        item_keywords=m.item_keywords or [],
        suggested_debit_account=m.suggested_debit_account,
        suggested_credit_account=m.suggested_credit_account,
        suggested_tax_accounts=m.suggested_tax_accounts or {},
        suggested_cost_center=m.suggested_cost_center,
        confidence_score=m.confidence_score,
        approval_count=m.approval_count,
        edit_count=m.edit_count,
        last_approved_at=m.last_approved_at,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class RuleRepository(RuleRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def create(self, rule: AccountingRule) -> AccountingRule:
        m = AccountingRuleModel(
            match_key_type=rule.match_key_type,
            issuer_nit=rule.issuer_nit,
            ciiu_code=rule.ciiu_code,
            item_keywords=rule.item_keywords or [],
            suggested_debit_account=rule.suggested_debit_account,
            suggested_credit_account=rule.suggested_credit_account,
            suggested_tax_accounts=rule.suggested_tax_accounts or {},
            suggested_cost_center=rule.suggested_cost_center,
            confidence_score=rule.confidence_score,
            approval_count=rule.approval_count,
            edit_count=rule.edit_count,
            last_approved_at=rule.last_approved_at,
            is_active=rule.is_active,
        )
        self.db.add(m)
        self.db.flush()

        if rule.description_embedding:
            emb_str = f"[{','.join(map(str, rule.description_embedding))}]"
            self.db.execute(
                text(
                    "UPDATE accounting_rules SET description_embedding = CAST(:emb AS vector) WHERE id = :id"
                ),
                {"emb": emb_str, "id": m.id},
            )

        self.db.commit()
        self.db.refresh(m)
        rule.id = m.id
        rule.created_at = m.created_at
        rule.updated_at = m.updated_at
        return rule

    def get_by_id(self, rule_id: int) -> Optional[AccountingRule]:
        m = self.db.query(AccountingRuleModel).filter(AccountingRuleModel.id == rule_id).first()
        return _to_entity(m) if m else None

    def list(
        self,
        nit: Optional[str] = None,
        match_key_type: Optional[str] = None,
        min_confidence: Optional[float] = None,
        is_active: Optional[bool] = None,
    ) -> List[AccountingRule]:
        q = self.db.query(AccountingRuleModel)
        if nit is not None:
            q = q.filter(AccountingRuleModel.issuer_nit == nit)
        if match_key_type is not None:
            q = q.filter(AccountingRuleModel.match_key_type == match_key_type)
        if min_confidence is not None:
            q = q.filter(AccountingRuleModel.confidence_score >= min_confidence)
        if is_active is not None:
            q = q.filter(AccountingRuleModel.is_active == is_active)
        return [_to_entity(m) for m in q.order_by(AccountingRuleModel.confidence_score.desc()).all()]

    def update(self, rule: AccountingRule) -> AccountingRule:
        m = self.db.query(AccountingRuleModel).filter(AccountingRuleModel.id == rule.id).first()
        if not m:
            return rule
        m.confidence_score = rule.confidence_score
        m.approval_count = rule.approval_count
        m.edit_count = rule.edit_count
        m.last_approved_at = rule.last_approved_at
        m.is_active = rule.is_active
        m.suggested_debit_account = rule.suggested_debit_account
        m.suggested_credit_account = rule.suggested_credit_account
        m.suggested_tax_accounts = rule.suggested_tax_accounts
        m.suggested_cost_center = rule.suggested_cost_center
        m.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(m)
        rule.updated_at = m.updated_at
        return rule

    def find_by_nit(self, nit: str) -> List[AccountingRule]:
        rows = (
            self.db.query(AccountingRuleModel)
            .filter(
                AccountingRuleModel.issuer_nit == nit,
                AccountingRuleModel.match_key_type == "nit_only",
                AccountingRuleModel.is_active.is_(True),
            )
            .order_by(AccountingRuleModel.confidence_score.desc())
            .all()
        )
        return [_to_entity(m) for m in rows]

    def search_semantic(self, nit: str, embedding: List[float], top_k: int = 5) -> List[Dict]:
        emb_str = f"[{','.join(map(str, embedding))}]"
        rows = self.db.execute(
            text("""
                SELECT id,
                       1 - (description_embedding <=> CAST(:emb AS vector)) AS similarity
                FROM accounting_rules
                WHERE issuer_nit = :nit
                  AND match_key_type = 'nit_semantic'
                  AND description_embedding IS NOT NULL
                  AND is_active = TRUE
                ORDER BY description_embedding <=> CAST(:emb AS vector)
                LIMIT :top_k
            """),
            {"emb": emb_str, "nit": nit, "top_k": top_k},
        ).fetchall()
        return [{"rule_id": r[0], "similarity": round(float(r[1]), 4)} for r in rows]

    def search_by_keywords(self, keywords: List[str], top_k: int = 5) -> List[AccountingRule]:
        if not keywords:
            return []
        rows = self.db.execute(
            text("""
                SELECT id FROM accounting_rules
                WHERE match_key_type = 'keyword_only'
                  AND is_active = TRUE
                  AND item_keywords && CAST(:kw AS text[])
                ORDER BY confidence_score DESC
                LIMIT :top_k
            """),
            {"kw": keywords, "top_k": top_k},
        ).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return []
        results = (
            self.db.query(AccountingRuleModel)
            .filter(AccountingRuleModel.id.in_(ids))
            .order_by(AccountingRuleModel.confidence_score.desc())
            .all()
        )
        return [_to_entity(m) for m in results]
