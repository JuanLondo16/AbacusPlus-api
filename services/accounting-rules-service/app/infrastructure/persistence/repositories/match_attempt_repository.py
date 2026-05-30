import logging
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.entities.rule_match_attempt import RuleMatchAttempt
from app.domain.ports.repositories import MatchAttemptRepositoryPort
from app.infrastructure.persistence.models.rule_match_attempt import RuleMatchAttemptModel

logger = logging.getLogger(__name__)


def _to_entity(m: RuleMatchAttemptModel) -> RuleMatchAttempt:
    return RuleMatchAttempt(
        id=m.id,
        document_id=m.document_id,
        rule_id=m.rule_id,
        match_level=m.match_level,
        match_key_type=m.match_key_type,
        confidence_at_match=m.confidence_at_match,
        llm_used_context=m.llm_used_context,
        final_approved=m.final_approved,
        suggested_payload=m.suggested_payload or {},
        created_at=m.created_at,
    )


class MatchAttemptRepository(MatchAttemptRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def create(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        m = RuleMatchAttemptModel(
            document_id=attempt.document_id,
            rule_id=attempt.rule_id,
            match_level=attempt.match_level,
            match_key_type=attempt.match_key_type,
            confidence_at_match=attempt.confidence_at_match,
            llm_used_context=attempt.llm_used_context,
            final_approved=attempt.final_approved,
            suggested_payload=attempt.suggested_payload or {},
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        attempt.id = m.id
        attempt.created_at = m.created_at
        return attempt

    def get_latest_by_document(self, document_id: int) -> Optional[RuleMatchAttempt]:
        m = (
            self.db.query(RuleMatchAttemptModel)
            .filter(RuleMatchAttemptModel.document_id == document_id)
            .order_by(RuleMatchAttemptModel.created_at.desc())
            .first()
        )
        return _to_entity(m) if m else None

    def update(self, attempt: RuleMatchAttempt) -> RuleMatchAttempt:
        m = (
            self.db.query(RuleMatchAttemptModel)
            .filter(RuleMatchAttemptModel.id == attempt.id)
            .first()
        )
        if not m:
            return attempt
        m.final_approved = attempt.final_approved
        m.llm_used_context = attempt.llm_used_context
        self.db.commit()
        self.db.refresh(m)
        return attempt

    def stats(self) -> Dict:
        total = self.db.query(func.count(RuleMatchAttemptModel.id)).scalar() or 0

        level_counts = (
            self.db.query(
                RuleMatchAttemptModel.match_level,
                func.count(RuleMatchAttemptModel.id),
            )
            .group_by(RuleMatchAttemptModel.match_level)
            .all()
        )
        by_level = {row[0]: row[1] for row in level_counts}

        with_context = (
            self.db.query(func.count(RuleMatchAttemptModel.id))
            .filter(RuleMatchAttemptModel.match_level.in_(["HIT", "PARTIAL"]))
            .scalar()
            or 0
        )
        approved_no_edit = (
            self.db.query(func.count(RuleMatchAttemptModel.id))
            .filter(
                RuleMatchAttemptModel.match_level.in_(["HIT", "PARTIAL"]),
                RuleMatchAttemptModel.final_approved.is_(True),
            )
            .scalar()
            or 0
        )

        key_type_counts = (
            self.db.query(
                RuleMatchAttemptModel.match_key_type,
                func.count(RuleMatchAttemptModel.id),
            )
            .filter(RuleMatchAttemptModel.match_key_type.isnot(None))
            .group_by(RuleMatchAttemptModel.match_key_type)
            .all()
        )

        return {
            "total": total,
            "by_level": by_level,
            "with_context": with_context,
            "approved_no_edit": approved_no_edit,
            "by_key_type": {row[0]: row[1] for row in key_type_counts},
        }
