from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.retention_criteria import RetentionCriterion


class RetentionCriteriaRepository:
    """RF-08 · Criterios de retención del contador, por tenant."""

    def __init__(self, db: Session):
        self._db = db

    def list_all(self, only_active: bool = True) -> list[RetentionCriterion]:
        """Todos los criterios. Se devuelven completos, nunca por similitud.

        El orden es estable (tema y luego id) para que dos ejecuciones sobre los mismos datos
        construyan el mismo prompt: en una decisión tributaria, la misma factura debe producir
        siempre la misma sugerencia, y un orden variable la haría fluctuar.
        """
        query = self._db.query(RetentionCriterion)
        if only_active:
            query = query.filter(RetentionCriterion.activo.is_(True))
        return query.order_by(RetentionCriterion.tema, RetentionCriterion.id).all()

    def count(self) -> int:
        return self._db.query(RetentionCriterion).count()

    def replace_all(self, criterios: list[dict]) -> list[RetentionCriterion]:
        """Reemplaza el conjunto completo de criterios del tenant.

        Se reemplaza en bloque y no fila a fila porque los criterios se leen y se revisan como
        un cuerpo único —el cuestionario del contador—, no como registros sueltos. Editar uno
        sin ver los demás es justo como se introducen contradicciones entre ellos.
        """
        self._db.query(RetentionCriterion).delete(synchronize_session=False)
        filas = [RetentionCriterion(**c) for c in criterios]
        self._db.add_all(filas)
        self._db.commit()
        return self.list_all(only_active=False)

    def seed_if_empty(self, criterios: list[dict]) -> int:
        """Carga los criterios por defecto solo si el tenant no tiene ninguno.

        No destructivo a propósito: re-aprovisionar un cliente no puede pisar los criterios
        que su contador haya ajustado. Devuelve cuántos se cargaron (0 si ya había).
        """
        if self.count() > 0:
            return 0
        self._db.add_all([RetentionCriterion(**c) for c in criterios])
        self._db.commit()
        return len(criterios)
