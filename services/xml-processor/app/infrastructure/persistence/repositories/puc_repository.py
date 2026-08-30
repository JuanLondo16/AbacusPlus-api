from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.puc import PucAccount


class PucRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> list[PucAccount]:
        return (
            self._db.query(PucAccount)
            .filter(PucAccount.is_active.is_(True))
            .order_by(PucAccount.code)
            .all()
        )

    def upsert_many(
        self, items: list[dict[str, Any]], deactivate_missing: bool = False
    ) -> tuple[int, int]:
        """Proyecta el plan de cuentas importado sobre `puc_accounts`.

        La conciliación es por `code`, que es la llave natural de una cuenta contable y la
        que referencia `document_details.code`. Las cuentas ausentes en el origen se
        desactivan —nunca se borran— para no invalidar asignaciones históricas; por defecto
        ni siquiera se desactivan, ya que un Excel puede ser parcial.

        Retorna (creadas, actualizadas).
        """
        existing = {acc.code: acc for acc in self._db.query(PucAccount).all()}
        seen: set[str] = set()
        created = updated = 0

        for item in items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            name = str(item.get("name") or "").strip() or code
            level = item.get("level")
            level = int(level) if level is not None else None
            is_active = bool(item.get("active", True))
            # `None` significa que el origen no informó el dato, y se distingue de `False`:
            # sobrescribir con None un valor ya calculado perdería la única señal que
            # permite descartar las cuentas agrupadoras.
            accepts = item.get("accepts_movements")
            accepts = bool(accepts) if accepts is not None else None
            seen.add(code)

            current = existing.get(code)
            if current is None:
                self._db.add(
                    PucAccount(
                        code=code,
                        name=name,
                        level=level,
                        is_active=is_active,
                        accepts_movements=accepts,
                    )
                )
                created += 1
            elif (
                current.name != name
                or current.is_active != is_active
                or (level is not None and current.level != level)
                or (accepts is not None and current.accepts_movements != accepts)
            ):
                current.name = name
                current.is_active = is_active
                if level is not None:
                    current.level = level
                if accepts is not None:
                    current.accepts_movements = accepts
                updated += 1

        if deactivate_missing:
            for code, current in existing.items():
                if code not in seen and current.is_active:
                    current.is_active = False
                    updated += 1

        self._db.commit()
        return created, updated
