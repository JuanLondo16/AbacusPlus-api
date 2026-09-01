from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.payment_type import PaymentType


class PaymentTypeRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(
        self,
        payment_types: Iterable[dict],
        deactivate_missing: bool = False,
        replace: bool = False,
    ) -> int:
        """`replace=True` borra TODO el catálogo antes de insertar (modo `replace` del import
        por Excel). `deactivate_missing=True` solo borra los ids ausentes del lote (lo usa el
        sync de SIIGO). Nada se confirma hasta el `commit()` final: si algo falla a mitad de
        camino, el `rollback()` deshace también el borrado.

        El Excel nunca trae el id de SIIGO (esa columna ni existe en la plantilla), así que el
        emparejamiento por `id` de abajo solo aplica a filas que sí lo traen (sync de SIIGO).
        Para las demás, la identidad es `name` —único en la tabla, e igual a lo que este
        endpoint documenta ("idempotente por name")—. Antes se emparejaba también por `id`
        aunque viniera `None`, lo que nunca encuentra fila (`id` es NOT NULL) y terminaba
        intentando crear una fila con `id=NULL`: como la columna nació sin autoincrement,
        Postgres la rechazaba en la primera fila de cualquier importación por Excel.
        """
        items = list(payment_types)
        incoming_ids = [item["id"] for item in items if item.get("id") is not None]

        try:
            if replace:
                self.db.query(PaymentType).delete(synchronize_session=False)
                self.db.flush()
            elif deactivate_missing and incoming_ids:
                self.db.query(PaymentType).filter(PaymentType.id.notin_(incoming_ids)).delete(
                    synchronize_session=False
                )

            synced = 0
            for item in items:
                siigo_id = item.get("id")
                name = str(item["name"]).strip()

                if siigo_id is not None:
                    model = (
                        self.db.query(PaymentType).filter(PaymentType.id == siigo_id).one_or_none()
                    )
                    if model is None:
                        model = PaymentType(id=siigo_id)
                        self.db.add(model)
                else:
                    model = self.db.query(PaymentType).filter(PaymentType.name == name).one_or_none()
                    if model is None:
                        model = PaymentType(name=name)
                        self.db.add(model)

                model.name = name
                model.type = item["type"]
                model.active = item.get("active", True)
                synced += 1

            self.db.commit()
            return synced
        except Exception:
            self.db.rollback()
            raise

    def list(self, active: Optional[bool] = None) -> list[PaymentType]:
        query = self.db.query(PaymentType)
        if active is not None:
            query = query.filter(PaymentType.active.is_(active))
        return query.order_by(PaymentType.name.asc()).all()
