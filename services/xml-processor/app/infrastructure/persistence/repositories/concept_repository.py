from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from app.infrastructure.persistence.models.concept import Concept, ConceptDescription
from app.utils.smart_match import smart_match
from app.domain.ports.repositories import ConceptRepositoryPort


CONCEPT_MATCH_THRESHOLD = 80


class ConceptRepository(ConceptRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def get_descriptions_by_receiver(self, receiver_nit: str) -> List[ConceptDescription]:
        return self.db.query(ConceptDescription).filter(
            ConceptDescription.receiver_nit == receiver_nit
        ).all()

    def find_matching_description(
        self, receiver_nit: str, description: str
    ) -> Optional[ConceptDescription]:
        concepts = self.get_descriptions_by_receiver(receiver_nit)
        for concept in concepts:
            if smart_match(concept.description, description) > CONCEPT_MATCH_THRESHOLD:
                return concept
        return None

    def create_description(self, concept_desc: ConceptDescription) -> ConceptDescription:
        self.db.add(concept_desc)
        self.db.commit()
        self.db.refresh(concept_desc)
        return concept_desc

    def get_accounts_by_description_ids(self, description_ids: List[int]) -> Dict[int, str]:
        """Retorna {concept_description_id: account_number} para los IDs dados."""
        if not description_ids:
            return {}
        rows = (
            self.db.query(ConceptDescription.id, Concept.account_number)
            .join(Concept, Concept.id == ConceptDescription.concept_id)
            .filter(ConceptDescription.id.in_(description_ids))
            .filter(Concept.account_number != "")
            .all()
        )
        return {row[0]: row[1] for row in rows}
