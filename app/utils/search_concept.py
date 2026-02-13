from app.core.config import get_db
from app.models.concept import ConceptDescription
from app.utils.smart_match import smart_match

def search_concept(description: str, receiver_nit: str):
    db = next(get_db())
    concepts = db.query(ConceptDescription).filter(ConceptDescription.receiver_nit == receiver_nit).all()
    for concept in concepts:
        if smart_match(concept.description, description) > 80:
            return concept
    return None

    