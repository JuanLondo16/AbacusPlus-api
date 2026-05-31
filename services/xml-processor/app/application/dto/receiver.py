from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReceiverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    nit: str
    phone: Optional[str] = None
    email: Optional[str] = None
