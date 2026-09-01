"""
RF-02 — `GET /catalog/taxes`, el endpoint que alimenta el selector de retenciones.

Desde la migración del 2026-08-31 el catálogo vive partido en dos tablas físicas:
`integration_taxes` (impuestos reales del documento) e `integration_retentions`
(retenciones, con el municipio/concepto/base mínima de ReteICA ya en la misma fila). Antes de
esto el endpoint leía enteramente de `integration_taxes`; estos tests fijan que `ambito`
reparte la lectura entre las dos tablas correctamente, y que `ambito=retenciones` ya no puede
quedar vacío solo porque las retenciones se movieron de tabla.
"""

import app.infrastructure.persistence.models.integration_retention  # noqa: F401
import app.infrastructure.persistence.models.integration_tax  # noqa: F401
import pytest
from app.adapters.api.routers.catalog import get_taxes
from app.infrastructure.persistence.models.integration_retention import IntegrationRetention
from app.infrastructure.persistence.models.integration_tax import IntegrationTax
from app.infrastructure.persistence.repositories.integration_retention_repository import (
    IntegrationRetentionRepository,
)
from app.infrastructure.persistence.repositories.integration_tax_repository import (
    IntegrationTaxRepository,
)


@pytest.fixture
def catalogo_separado(db_session):
    """Catálogo post-migración: impuestos y retenciones en sus tablas propias."""
    db_session.add_all(
        [
            IntegrationTax(id=1, name="IVA 19%", type="IVA", percentage=19.0, active=True),
            IntegrationTax(
                id=2, name="Impoconsumo 8%", type="Impoconsumo", percentage=8.0, active=True
            ),
        ]
    )
    db_session.add_all(
        [
            IntegrationRetention(
                id=101,
                name="ReteICA Bogotá D.C. · servicios",
                type="reteica",
                percentage=9.66,
                active=True,
                municipality_code="11001",
                municipality_name="Bogotá D.C.",
                retention_concept="servicios",
                minimum_base_uvt=4.0,
            ),
            IntegrationRetention(
                id=102, name="ReteIVA 15%", type="reteiva", percentage=15.0, active=True
            ),
            IntegrationRetention(
                id=103, name="Retefuente 2.5%", type="retefuente", percentage=2.5, active=True
            ),
            IntegrationRetention(
                id=104, name="autorretencion", type="autorretencion", percentage=0.4, active=True
            ),
            IntegrationRetention(
                id=105,
                name="ReteICA genérica (desactivada por el backfill)",
                type="reteica",
                percentage=6.9,
                active=False,
            ),
        ]
    )
    db_session.commit()
    return db_session


@pytest.fixture
def tax_repo(catalogo_separado):
    return IntegrationTaxRepository(catalogo_separado)


@pytest.fixture
def retention_repo(catalogo_separado):
    return IntegrationRetentionRepository(catalogo_separado)


class TestAmbitoRetenciones:
    """Debe leer de `integration_retentions`, no de `integration_taxes`."""

    def test_devuelve_reteica_y_reteiva_de_la_tabla_nueva(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="retenciones", repo=tax_repo, retention_repo=retention_repo)

        assert {r.id for r in resultado} == {101, 102}

    def test_retefuente_y_autorretencion_no_se_ofrecen(self, tax_repo, retention_repo):
        """SIIGO las rechaza en `POST /v1/purchases`: no deben llegar al selector."""
        resultado = get_taxes(ambito="retenciones", repo=tax_repo, retention_repo=retention_repo)

        assert 103 not in {r.id for r in resultado}
        assert 104 not in {r.id for r in resultado}

    def test_las_reteica_desactivadas_no_se_ofrecen(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="retenciones", repo=tax_repo, retention_repo=retention_repo)

        assert 105 not in {r.id for r in resultado}

    def test_la_fila_reteica_trae_su_municipio_y_base_minima_sin_cruzar_nada(
        self, tax_repo, retention_repo
    ):
        """Es el punto entero de la migración: la fila ya es autosuficiente."""
        resultado = get_taxes(ambito="retenciones", repo=tax_repo, retention_repo=retention_repo)

        reteica = next(r for r in resultado if r.id == 101)
        assert reteica.municipality_code == "11001"
        assert reteica.municipality_name == "Bogotá D.C."
        assert reteica.retention_concept == "servicios"
        assert reteica.minimum_base_uvt == 4.0

    def test_las_filas_que_no_son_reteica_no_traen_municipio(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="retenciones", repo=tax_repo, retention_repo=retention_repo)

        reteiva = next(r for r in resultado if r.id == 102)
        assert reteiva.municipality_code is None


class TestAmbitoLinea:
    """No debe verse afectado por la separación: sigue leyendo `integration_taxes`."""

    def test_devuelve_solo_los_impuestos_de_linea(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="linea", repo=tax_repo, retention_repo=retention_repo)

        assert {r.id for r in resultado} == {1, 2}

    def test_ninguna_retencion_se_cuela_en_linea(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="linea", repo=tax_repo, retention_repo=retention_repo)

        assert {r.id for r in resultado}.isdisjoint({101, 102, 103, 104})


class TestAmbitoTodos:
    """Resuelve el nombre de cualquier `tax_id` ya registrado, venga de la tabla que venga."""

    def test_combina_las_dos_tablas(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="todos", repo=tax_repo, retention_repo=retention_repo)

        ids = {r.id for r in resultado}
        assert ids == {1, 2, 101, 102, 103, 104}

    def test_no_filtra_por_tipo_practicable(self, tax_repo, retention_repo):
        """A diferencia de `retenciones`, aquí SÍ debe verse Retefuente y Autorretención."""
        resultado = get_taxes(ambito="todos", repo=tax_repo, retention_repo=retention_repo)

        assert {103, 104}.issubset({r.id for r in resultado})

    def test_las_desactivadas_no_aparecen_ni_en_todos(self, tax_repo, retention_repo):
        resultado = get_taxes(ambito="todos", repo=tax_repo, retention_repo=retention_repo)

        assert 105 not in {r.id for r in resultado}
