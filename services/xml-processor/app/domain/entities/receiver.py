from dataclasses import dataclass
from typing import Optional


@dataclass
class ReceiverEntity:
    name: str
    nit: str
    dv: int
    email: str
    phone: Optional[str] = None
    template: Optional[str] = None
    id: Optional[int] = None
