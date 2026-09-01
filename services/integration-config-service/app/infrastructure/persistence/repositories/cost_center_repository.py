from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.cost_center import CostCenter


class CostCenterRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(
        self,
        cost_centers: Iterable[dict],
        deactivate_missing: bool = False,
        replace: bool = False,
    ) -> int:
        """`replace=True` borra TODO el catálogo antes de insertar (modo `replace` del import
        por Excel). `deactivate_missing=True` solo borra los códigos ausentes del lote (lo usa
        el sync de SIIGO). Nada se confirma hasta el `commit()` final: si algo falla a mitad
        de camino, el `rollback()` deshace también el borrado, así que el catálogo nunca queda
        vacío por un archivo que fallaba en la fila 50.
        """
        items = list(cost_centers)
        incoming_codes = [str(item["code"]) for item in items if item.get("code")]

        try:
            if replace:
                self.db.query(CostCenter).delete(synchronize_session=False)
                self.db.flush()
            elif deactivate_missing and incoming_codes:
                self.db.query(CostCenter).filter(CostCenter.code.notin_(incoming_codes)).delete(
                    synchronize_session=False
                )

            synced = 0
            for cost_center in items:
                code = str(cost_center["code"])
                model = self.db.query(CostCenter).filter(CostCenter.code == code).one_or_none()
                if model is None:
                    model = CostCenter(code=code)
                    self.db.add(model)

                model.external_id = cost_center.get("external_id")
                model.name = cost_center["name"]
                model.active = cost_center.get("active", True)
                model.raw_payload = cost_center.get("raw_payload", {})
                synced += 1

            self.db.commit()
            return synced
        except Exception:
            self.db.rollback()
            raise

    def list(self, active: Optional[bool] = None) -> list[CostCenter]:
        query = self.db.query(CostCenter)
        if active is not None:
            query = query.filter(CostCenter.active.is_(active))
        return query.order_by(CostCenter.code.asc()).all()
