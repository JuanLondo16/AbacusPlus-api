from typing import List, Optional
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.system_prompt import SystemPrompt


class SystemPromptRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_all(self) -> List[SystemPrompt]:
        return self._db.query(SystemPrompt).order_by(SystemPrompt.id).all()

    def get_active(self) -> Optional[SystemPrompt]:
        return self._db.query(SystemPrompt).filter(SystemPrompt.is_active.is_(True)).first()

    def get_by_id(self, prompt_id: int) -> Optional[SystemPrompt]:
        return self._db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()

    def create(self, name: str, content: str) -> SystemPrompt:
        prompt = SystemPrompt(name=name, content=content, is_active=False)
        self._db.add(prompt)
        self._db.commit()
        self._db.refresh(prompt)
        return prompt

    def activate(self, prompt_id: int) -> Optional[SystemPrompt]:
        # Desactiva todos y activa el seleccionado
        self._db.query(SystemPrompt).update({"is_active": False})
        prompt = self._db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).first()
        if prompt:
            prompt.is_active = True
            self._db.commit()
            self._db.refresh(prompt)
        return prompt

    def create_default_if_none(self) -> None:
        if self._db.query(SystemPrompt).count() == 0:
            default = SystemPrompt(
                name="PUC Colombia — Causación v1",
                content=(
                    "Eres un experto en contabilidad colombiana (Plan Único de Cuentas - PUC).\n"
                    "Dado el JSON de una factura electrónica DIAN, genera el asiento contable de causación.\n"
                    "Responde ÚNICAMENTE con JSON válido sin texto adicional, con este formato exacto:\n"
                    "{\"entries\": [{\"cuenta\": \"string\", \"nombre\": \"string\", "
                    "\"debito\": 0.0, \"credito\": 0.0, \"tercero\": \"string\", "
                    "\"centro_costo\": \"string\", \"descripcion\": \"string\"}]}\n"
                    "El total de débitos debe ser igual al total de créditos."
                ),
                is_active=True,
            )
            self._db.add(default)
            self._db.commit()
