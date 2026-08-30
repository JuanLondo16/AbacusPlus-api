from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChunkEntity:
    source_type: str
    content: str
    source_id: Optional[int] = None
    embedding: Optional[list[float]] = field(default=None)
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    #: RF-08: True solo cuando el chunk representa una causación contabilizada en SIIGO.
    is_validated: bool = False
    validated_at: Optional[datetime] = None
    siigo_id: Optional[str] = None
    #: RF-08: rasgos estructurados del caso (NIT, municipio, cuentas, tipos de retención)
    #: con los que se filtra en la búsqueda híbrida.
    metadata: dict = field(default_factory=dict)
