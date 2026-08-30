from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.cost_center import CostCenter


class CostCenterRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> list[CostCenter]:
        return (
            self._db.query(CostCenter)
            .filter(CostCenter.is_active.is_(True))
            .order_by(CostCenter.code)
            .all()
        )

    def get_by_id(self, cost_center_id: int) -> "CostCenter | None":
        """Devuelve el centro de costo por id, activo o no.

        Permite distinguir «no existe» de «existe pero está inactivo» sin traer todo el
        catálogo: validar la pertenencia de un solo id no debería costar N filas.
        """
        return self._db.query(CostCenter).filter(CostCenter.id == cost_center_id).one_or_none()

    def upsert_many(
        self, items: list[dict[str, Any]], deactivate_missing: bool = True
    ) -> tuple[int, int]:
        """Proyecta el catálogo sincronizado desde el proveedor externo sobre `cost_centers`.

        La conciliación es por `code` —no por `id`— porque `document_details.cost_center_id`
        referencia el `id` local: reasignarlo huerfanaría las asignaciones ya guardadas.
        Los centros ausentes en el origen se desactivan en lugar de borrarse, por la misma razón.

        Retorna (creados, actualizados).
        """
        existing = {cc.code: cc for cc in self._db.query(CostCenter).all()}
        seen: set[str] = set()
        created = updated = 0

        for item in items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            name = str(item.get("name") or "").strip() or code
            is_active = bool(item.get("active", True))
            seen.add(code)

            current = existing.get(code)
            if current is None:
                self._db.add(CostCenter(code=code, name=name, is_active=is_active))
                created += 1
            elif current.name != name or current.is_active != is_active:
                current.name = name
                current.is_active = is_active
                updated += 1

        if deactivate_missing:
            for code, current in existing.items():
                if code not in seen and current.is_active:
                    current.is_active = False
                    updated += 1

        self._db.commit()
        return created, updated
