from dataclasses import dataclass
from typing import Optional


@dataclass
class ConceptEntity:
    receiver_nit: str
    concept: str = ""
    concept_code: str = ""
    account_number: str = ""
    id: Optional[int] = None


@dataclass
class ConceptDescriptionEntity:
    receiver_nit: str
    description: str
    concept_id: Optional[int] = None
    id: Optional[int] = None
