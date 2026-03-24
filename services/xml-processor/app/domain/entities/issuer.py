from dataclasses import dataclass
from typing import Optional


@dataclass
class IssuerEntity:
    name: str
    nit: str
    dv: int
    email: str
    phone: Optional[str] = None
    account_number: Optional[str] = ""
    id: Optional[int] = None
