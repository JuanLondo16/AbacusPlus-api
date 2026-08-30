from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.retention_fuente import RetentionFuenteRate
from app.infrastructure.persistence.models.retention_ica import RetentionIcaRate


class RetentionRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_fuente_rates(self) -> list[RetentionFuenteRate]:
        return (
            self._db.query(RetentionFuenteRate)
            .order_by(RetentionFuenteRate.retention_concept, RetentionFuenteRate.taxpayer_type)
            .all()
        )

    def get_ica_rates(self) -> list[RetentionIcaRate]:
        # Orden estable por (municipio, concepto): es la clave de la tabla y el orden en que
        # el contador espera leerla. Además hace determinista el prompt de la sugerencia.
        return (
            self._db.query(RetentionIcaRate)
            .order_by(RetentionIcaRate.municipality_code, RetentionIcaRate.retention_concept)
            .all()
        )

    def import_rates(self, fuente_rows, ica_rows, *, replace: bool = False) -> tuple[int, int]:
        """Aplica la importación de tarifas en una sola transacción.

        `replace` decide qué se hace con lo que ya está cargado, con la misma semántica que la
        importación del plan de cuentas:

        - `False` (por defecto): **upsert**. Cada fila actualiza la tarifa existente o la crea.
          Lo que no venga en el archivo se conserva. Es el modo seguro: subir una hoja con dos
          conceptos corrige esos dos y no toca los demás.
        - `True`: **reemplazo**. Se vacía la tabla antes de cargar, de modo que el archivo pasa
          a ser la verdad completa. Es lo que se necesita en la re-importación anual de la
          tabla nacional, cuando además hay que dar de baja conceptos que ya no existen.

        En ambos modos, `None` significa que esa hoja no venía en el archivo y por tanto esa
        tabla **no se toca en absoluto**, ni siquiera con `replace=True`. Sin esa regla, subir
        solo ReteICA borraría la tabla nacional entera.
        """
        fuente_count = 0
        ica_count = 0

        if fuente_rows is not None:
            if replace:
                self._db.query(RetentionFuenteRate).delete(synchronize_session=False)
                # El DELETE debe estar aplicado antes de insertar: si no, la restricción
                # única (concepto, tipo_contribuyente) rechazaría las filas que se repiten
                # entre lo viejo y lo nuevo.
                self._db.flush()
                self._db.add_all([RetentionFuenteRate(**row) for row in fuente_rows])
            else:
                for row in fuente_rows:
                    existing = (
                        self._db.query(RetentionFuenteRate)
                        .filter(
                            RetentionFuenteRate.retention_concept == row["retention_concept"],
                            RetentionFuenteRate.taxpayer_type == row["taxpayer_type"],
                        )
                        .one_or_none()
                    )
                    if existing is None:
                        self._db.add(RetentionFuenteRate(**row))
                    else:
                        existing.minimum_base_uvt = row.get("minimum_base_uvt")
                        existing.minimum_base_pesos = row.get("minimum_base_pesos")
                        existing.rate_percentage = row["rate_percentage"]
            fuente_count = len(fuente_rows)

        if ica_rows is not None:
            if replace:
                self._db.query(RetentionIcaRate).delete(synchronize_session=False)
                self._db.flush()
                self._db.add_all([RetentionIcaRate(**row) for row in ica_rows])
            else:
                for row in ica_rows:
                    # La identidad de una tarifa de ReteICA es (municipio, concepto). Buscar
                    # solo por municipio devolvía varias filas en cuanto el contador cargaba
                    # las bandas por actividad, y `one_or_none()` reventaba; peor aún, en el
                    # caso de una sola fila habría machacado la tarifa de un concepto con la
                    # de otro.
                    existing = (
                        self._db.query(RetentionIcaRate)
                        .filter(
                            RetentionIcaRate.municipality_code == row["municipality_code"],
                            RetentionIcaRate.retention_concept == row["retention_concept"],
                        )
                        .one_or_none()
                    )
                    if existing is None:
                        self._db.add(RetentionIcaRate(**row))
                    else:
                        existing.municipality_name = row.get("municipality_name")
                        existing.percentage = row["percentage"]
            ica_count = len(ica_rows)

        self._db.commit()
        return fuente_count, ica_count
