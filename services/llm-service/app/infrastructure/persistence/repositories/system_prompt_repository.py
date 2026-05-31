from typing import Optional

from app.infrastructure.persistence.models.system_prompt import SystemPrompt
from sqlalchemy.orm import Session


class SystemPromptRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_all(self) -> list[SystemPrompt]:
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
            from app.application.use_cases.generate_accounting_entry import _DEFAULT_SYSTEM_PROMPT

            default = SystemPrompt(
                name="PUC Colombia — Causación v2",
                content=_DEFAULT_SYSTEM_PROMPT,
                is_active=True,
            )
            self._db.add(default)
            self._db.commit()
