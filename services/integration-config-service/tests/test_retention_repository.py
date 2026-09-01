"""`integration_retentions` — repositorio de retenciones (ReteICA, ReteIVA, Retefuente,
Autorretención).

Usa SQLite en memoria, igual que `test_retention_criteria.py`: lo que se prueba aquí es la
lógica de negocio del repositorio (idempotencia de la sincronización SIIGO, unicidad de
ReteICA por municipio+concepto), no artefactos específicos de PostgreSQL. Eso vive en
`test_retention_backfill.py`.
"""

import pytest
from app.infrastructure.config.database import Base
from app.infrastructure.persistence.models.retention import Retention  # noqa: F401
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Retention.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield RetentionRepository(session)
    finally:
        session.close()


class TestListado:
    def test_lista_vacia_al_principio(self, repo):
        assert repo.list() == []

    def test_filtra_por_activo(self, repo):
        repo.upsert_siigo_many(
            [
                {"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0, "active": True},
                {
                    "id": 2,
                    "name": "Retefuente 4%",
                    "type": "Retefuente",
                    "percentage": 4.0,
                    "active": False,
                },
            ]
        )

        assert [r.name for r in repo.list(active=True)] == ["ReteIVA 15%"]
        assert [r.name for r in repo.list(active=False)] == ["Retefuente 4%"]

    def test_filtra_por_tipo(self, repo):
        repo.upsert_siigo_many(
            [
                {"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0},
                {"id": 2, "name": "Retefuente 4%", "type": "Retefuente", "percentage": 4.0},
            ]
        )

        assert [r.name for r in repo.list(type="reteiva")] == ["ReteIVA 15%"]


class TestSyncSiigo:
    def test_conserva_el_id_de_siigo(self, repo):
        repo.upsert_siigo_many(
            [{"id": 10608, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0}]
        )

        fila = repo.get_by_id(10608)
        assert fila is not None
        assert fila.name == "ReteIVA 15%"
        assert fila.type == "reteiva"  # normalizado, no la grafía cruda de SIIGO

    def test_el_type_se_guarda_normalizado(self, repo):
        repo.upsert_siigo_many(
            [{"id": 1, "name": "Retefuente 4%", "type": "Retefuente", "percentage": 4.0}]
        )

        assert repo.get_by_id(1).type == "retefuente"

    def test_sincronizar_dos_veces_no_duplica(self, repo):
        item = {"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0}

        repo.upsert_siigo_many([item])
        repo.upsert_siigo_many([item])

        assert len(repo.list()) == 1

    def test_actualiza_el_porcentaje_si_cambia(self, repo):
        repo.upsert_siigo_many(
            [{"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0}]
        )
        repo.upsert_siigo_many(
            [{"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 10.0}]
        )

        assert float(repo.get_by_id(1).percentage) == 10.0

    # La reidentificación por nombre (`_reidentificar`) usa `now()` de PostgreSQL igual que
    # `TaxRepository._reidentificar`, y por lo mismo se prueba contra Postgres real, no
    # SQLite — ver `TestReidentificacionDeRetenciones` en `test_retention_backfill.py`.


class TestImportacionIca:
    _FILA_BOGOTA = {
        "municipality_code": "11001",
        "municipality_name": "Bogotá D.C.",
        "retention_concept": "servicios",
        "percentage": 9.66,
        "minimum_base_uvt": 4.0,
    }

    def test_carga_una_tarifa_nueva(self, repo):
        cargadas = repo.upsert_ica_rows([self._FILA_BOGOTA])

        assert cargadas == 1
        fila = repo.list(type="reteica")[0]
        assert fila.municipality_code == "11001"
        assert fila.retention_concept == "servicios"
        assert float(fila.minimum_base_uvt) == 4.0
        assert "Bogotá" in fila.name

    def test_upsert_por_municipio_y_concepto_no_duplica(self, repo):
        repo.upsert_ica_rows([self._FILA_BOGOTA])
        repo.upsert_ica_rows([{**self._FILA_BOGOTA, "percentage": 10.0}])

        filas = repo.list(type="reteica")
        assert len(filas) == 1
        assert float(filas[0].percentage) == 10.0

    def test_un_municipio_puede_tener_varios_conceptos(self, repo):
        repo.upsert_ica_rows(
            [self._FILA_BOGOTA, {**self._FILA_BOGOTA, "retention_concept": "compras", "percentage": 11.04}]
        )

        assert len(repo.list(type="reteica")) == 2

    def test_replace_solo_borra_reteica_no_las_demas(self, repo):
        repo.upsert_siigo_many(
            [{"id": 1, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0}]
        )
        repo.upsert_ica_rows([self._FILA_BOGOTA])

        repo.upsert_ica_rows(
            [{**self._FILA_BOGOTA, "municipality_code": "05001", "municipality_name": "Medellín"}],
            replace=True,
        )

        tipos_restantes = {r.type for r in repo.list()}
        assert tipos_restantes == {"reteiva", "reteica"}
        codigos_ica = {r.municipality_code for r in repo.list(type="reteica")}
        assert codigos_ica == {"05001"}
