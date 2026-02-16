from dataclasses import dataclass
from typing import Optional


@dataclass
class TaxEntity:
    receiver_nit: str
    tax: str
    percentage: float
    account_number: str = ""
    id: Optional[int] = None
