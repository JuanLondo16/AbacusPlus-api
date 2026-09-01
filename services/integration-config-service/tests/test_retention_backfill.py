"""Backfill que separa `integration_taxes` en impuestos y retenciones (2026-08-31).

Necesita PostgreSQL de verdad, no SQLite: se comprueba `information_schema`, columnas SERIAL
con `setval`, e índices únicos parciales (`WHERE type = 'reteica'`) — ninguna de las tres
cosas existe igual en SQLite. Mismo criterio que ya usa `test_tax_id_remap.py`.

El caso base reproduce el catálogo real de `abacus_t_ikbo` (33 filas en integration_taxes con
ids ya reidentificados a SIIGO, 3 tarifas de ReteICA en `retention_ica_rates`, 33 filas de
document_taxes) a escala reducida, para verificar exactamente las garantías que importan aquí:
el id se preserva cuando es posible, las referencias se reapuntan cuando no, nada se borra sin
haberse verificado antes, y correr el backfill dos veces no cambia el resultado.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://master:{pwd}@localhost:5433/abacus_test_taxes".format(
        pwd=os.getenv("DATABASE_PASSWORD", "master")
    ),
)

_ESQUEMA = """
DROP TABLE IF EXISTS document_taxes;
DROP TABLE IF EXISTS document_details;
DROP TABLE IF EXISTS retention_ica_rates;
DROP TABLE IF EXISTS integration_retentions;
DROP TABLE IF EXISTS integration_taxes;

CREATE TABLE integration_taxes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    percentage NUMERIC(10,4) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE integration_retentions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    type VARCHAR(50) NOT NULL,
    percentage NUMERIC(10,6) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    municipality_code VARCHAR(20),
    municipality_name VARCHAR(120),
    retention_concept VARCHAR(120),
    minimum_base_uvt NUMERIC(10,2),
    source VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_ir_ica ON integration_retentions (municipality_code, retention_concept)
    WHERE type = 'reteica';
CREATE UNIQUE INDEX uq_ir_name ON integration_retentions (name) WHERE type <> 'reteica';

CREATE TABLE retention_ica_rates (
    id SERIAL PRIMARY KEY,
    municipality_code VARCHAR(20) NOT NULL,
    municipality_name VARCHAR(120),
    percentage NUMERIC(10,6) NOT NULL,
    retention_concept VARCHAR(120) NOT NULL DEFAULT 'todos',
    minimum_base_uvt NUMERIC(10,2),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (municipality_code, retention_concept)
);

CREATE TABLE document_taxes (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER NOT NULL,
    value NUMERIC(18,2)
);

CREATE TABLE document_details (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER REFERENCES integration_taxes(id)
);
"""


@pytest.fixture
def engine():
    try:
        eng = create_engine(_URL)
        with eng.begin() as conexion:
            for sentencia in filter(None, (s.strip() for s in _ESQUEMA.split(";"))):
                conexion.execute(text(sentencia))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL de pruebas no disponible: {exc}")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    fabrica = sessionmaker(bind=engine)
    sesion = fabrica()
    yield sesion
    sesion.close()


def _sembrar_catalogo_real_reducido(session) -> None:
    """Una versión reducida y fiel del catálogo real de abacus_t_ikbo.

    Impuestos (quedan en integration_taxes): IVA, Impoconsumo.
    Retenciones (deben migrar): Retefuente, ReteICA, ReteIVA, Autorretencion.
    Los ids de retención (10596+) son mayores que los de retention_ica_rates (11-13): el
    caso común, sin colisión, donde el id original se preserva.
    """
    session.execute(
        text(
            "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
            "(10609, 'Impoconsumo 8%', 'Impoconsumo', 8.0, true),"
            "(20921, 'IVA 19%.', 'IVA', 19.0, true),"
            "(10596, 'Retefuente 11%', 'Retefuente', 11.0, true),"
            "(10603, 'ReteICA 9.66', 'ReteICA', 9.66, true),"
            "(10608, 'ReteIVA 15%', 'ReteIVA', 15.0, true),"
            "(20922, 'autorretención.', 'Autorretencion', 1.1, true)"
        )
    )
    session.execute(
        text(
            "INSERT INTO retention_ica_rates "
            "(id, municipality_code, municipality_name, percentage, retention_concept, "
            " minimum_base_uvt) VALUES "
            "(11, '11001', 'Bogotá D.C.', 9.66, 'servicios', 4.0),"
            "(12, '11001', 'Bogotá D.C.', 11.04, 'compras', 27.0),"
            "(13, '68001', 'Bucaramanga', 7.0, 'servicios', 25.0)"
        )
    )
    # document_taxes: retenciones (deben remapearse por valor, aunque el id se preserve) +
    # un impuesto (Impoconsumo, no debe tocarse nunca).
    session.execute(
        text(
            "INSERT INTO document_taxes (document_id, tax_id, value) VALUES "
            "(1, 10596, 1000), (1, 10608, 500), (2, 10603, 300), (3, 20922, 10), (4, 10609, 50)"
        )
    )
    # document_details: solo impuestos de línea, nunca retenciones (regla de negocio real).
    session.execute(
        text("INSERT INTO document_details (document_id, tax_id) VALUES (1, 20921), (1, 10609)")
    )
    session.commit()


def _run(engine):
    from app.infrastructure.persistence.retention_backfill import run

    return run(engine)


class TestElBackfillMueveLasRetenciones:
    def test_las_cuatro_retenciones_migran(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        reporte = _run(engine)

        assert reporte.taxes_migrated == 4  # retefuente, reteica, reteiva, autorretencion
        tipos = {
            fila[0]
            for fila in session.execute(text("SELECT type FROM integration_retentions")).fetchall()
        }
        assert tipos >= {"retefuente", "reteica", "reteiva", "autorretencion"}

    def test_los_impuestos_reales_no_se_tocan(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        _run(engine)

        restantes = {
            fila[0]
            for fila in session.execute(text("SELECT name FROM integration_taxes")).fetchall()
        }
        assert restantes == {"Impoconsumo 8%", "IVA 19%."}

    def test_el_id_original_se_preserva_cuando_es_posible(self, engine, session):
        """Los ids de integration_taxes YA SON los ids reales de SIIGO. Preservarlos evita
        romper el envío de ReteIVA a SIIGO al contabilizar."""
        _sembrar_catalogo_real_reducido(session)

        reporte = _run(engine)

        assert reporte.taxes_reused_id == 4
        assert reporte.taxes_remapped_id == 0
        ids = {
            fila[0]
            for fila in session.execute(
                text("SELECT id FROM integration_retentions WHERE type <> 'reteica'")
            ).fetchall()
        }
        assert ids == {10596, 10608, 20922}

    def test_retention_ica_rates_se_fusiona_con_su_municipio_y_concepto(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        reporte = _run(engine)

        assert reporte.ica_rates_migrated == 3
        filas = session.execute(
            text(
                "SELECT municipality_code, retention_concept, percentage, minimum_base_uvt "
                "FROM integration_retentions "
                "WHERE type = 'reteica' AND municipality_code IS NOT NULL "
                "ORDER BY municipality_code, retention_concept"
            )
        ).fetchall()
        assert [(c, k, float(p), float(b)) for c, k, p, b in filas] == [
            ("11001", "compras", 11.04, 27.0),
            ("11001", "servicios", 9.66, 4.0),
            ("68001", "servicios", 7.0, 25.0),
        ]

    def test_la_tarifa_generica_de_reteica_migra_desactivada(self, engine, session):
        """"ReteICA 9.66" (de integration_taxes, sin municipio) es exactamente el dato que
        motivó esta migración: casi nunca coincidía con la tarifa real de un municipio. Se
        conserva por los document_taxes que la citan, pero no puede volver a ofrecerse."""
        _sembrar_catalogo_real_reducido(session)

        _run(engine)

        fila = session.execute(
            text(
                "SELECT active, municipality_code FROM integration_retentions "
                "WHERE id = 10603"
            )
        ).first()
        assert fila is not None
        assert fila[0] is False
        assert fila[1] is None

    def test_las_referencias_de_document_taxes_quedan_resueltas(self, engine, session):
        """No importa si el id cambió o no: al final, cada tax_id de retención resuelve en
        integration_retentions, y el de impuesto sigue resolviendo en integration_taxes."""
        _sembrar_catalogo_real_reducido(session)

        _run(engine)

        huerfanas_retenciones = session.execute(
            text(
                "SELECT count(*) FROM document_taxes d "
                "LEFT JOIN integration_retentions r ON r.id = d.tax_id "
                "LEFT JOIN integration_taxes t ON t.id = d.tax_id "
                "WHERE r.id IS NULL AND t.id IS NULL"
            )
        ).scalar()
        assert huerfanas_retenciones == 0

        # El impuesto (Impoconsumo) nunca se tocó: sigue apuntando a integration_taxes.
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 4")
            ).scalar()
            == 10609
        )

    def test_document_details_no_se_rompe_por_la_fk(self, engine, session):
        """document_details.tax_id lleva FK a integration_taxes: sus impuestos de línea
        (IVA/Impoconsumo) deben seguir resolviendo ahí sin que la FK se rompa."""
        _sembrar_catalogo_real_reducido(session)

        _run(engine)

        valores = {
            fila[0]
            for fila in session.execute(
                text("SELECT tax_id FROM document_details WHERE document_id = 1")
            ).fetchall()
        }
        assert valores == {20921, 10609}
        # La FK sigue viva: ambos ids siguen existiendo en integration_taxes.
        existentes = {
            fila[0]
            for fila in session.execute(
                text("SELECT id FROM integration_taxes WHERE id IN (20921, 10609)")
            ).fetchall()
        }
        assert existentes == {20921, 10609}

    def test_no_quedan_huerfanos_ni_bloqueos(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        reporte = _run(engine)

        assert reporte.orphans == []
        assert reporte.taxes_kept_due_to_reference == []

    def test_las_retenciones_migradas_se_borran_de_integration_taxes(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        reporte = _run(engine)

        assert reporte.taxes_deleted == 4
        restantes = session.execute(
            text(
                "SELECT count(*) FROM integration_taxes WHERE id IN "
                "(10596, 10603, 10608, 20922)"
            )
        ).scalar()
        assert restantes == 0


class TestIdempotencia:
    def test_correrlo_dos_veces_no_duplica_ni_cambia_nada(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        _run(engine)
        segunda = _run(engine)

        assert segunda.taxes_migrated == 0  # ya no queda nada que migrar en integration_taxes
        assert segunda.ica_rates_migrated == 0
        assert segunda.ica_rates_already_present == 3

        total_retenciones = session.execute(
            text("SELECT count(*) FROM integration_retentions")
        ).scalar()
        assert total_retenciones == 4 + 3  # 4 de integration_taxes + 3 de retention_ica_rates

    def test_las_referencias_siguen_correctas_tras_la_segunda_corrida(self, engine, session):
        _sembrar_catalogo_real_reducido(session)

        _run(engine)
        _run(engine)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 1 AND value = 1000")
            ).scalar()
            == 10596
        )


class TestColisionDeId:
    """Caso adverso: el id de una retención de integration_taxes coincide con un id ya
    ocupado en integration_retentions (por ejemplo, una fila de ReteICA migrada antes con
    ese mismo número). Debe generarse un id nuevo y remapear document_taxes — es el único
    camino donde el mapa de reemplazo se ejercita de verdad.
    """

    def test_genera_id_nuevo_y_remapea_las_referencias(self, engine, session):
        # Se siembra una fila en integration_retentions que YA ocupa el id 10596.
        session.execute(
            text(
                "INSERT INTO integration_retentions "
                "(id, name, type, percentage, active, municipality_code, retention_concept, source) "
                "VALUES (10596, 'ReteICA ocupante', 'reteica', 1.0, true, '05001', 'todos', 'excel')"
            )
        )
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
                "(10596, 'Retefuente 11%', 'Retefuente', 11.0, true)"
            )
        )
        session.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (9, 10596, 100)")
        )
        session.commit()

        reporte = _run(engine)

        assert reporte.taxes_remapped_id == 1
        nuevo_id = session.execute(
            text("SELECT id FROM integration_retentions WHERE name = 'Retefuente 11%'")
        ).scalar()
        assert nuevo_id != 10596
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 9")
            ).scalar()
            == nuevo_id
        )
        # La fila que ya ocupaba el id no se tocó.
        assert (
            session.execute(
                text("SELECT name FROM integration_retentions WHERE id = 10596")
            ).scalar()
            == "ReteICA ocupante"
        )


class TestSinRetentionIcaRates:
    """El tenant puede no tener aún la tabla (xml-processor sin provisionar todavía). El
    backfill de integration_taxes debe seguir funcionando igual."""

    def test_funciona_sin_la_tabla_de_ica(self, engine, session):
        session.execute(text("DROP TABLE retention_ica_rates"))
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
                "(10596, 'Retefuente 11%', 'Retefuente', 11.0, true)"
            )
        )
        session.commit()

        reporte = _run(engine)

        assert reporte.taxes_migrated == 1
        assert reporte.ica_rates_scanned == 0


class TestReidentificacionDeRetenciones:
    """`RetentionRepository.upsert_siigo_many` adopta el id de SIIGO en una fila local
    heredada — mismo mecanismo que ya prueba `test_tax_id_remap.py` para `TaxRepository`, y
    necesita PostgreSQL real por lo mismo: usa `now()` e `information_schema` para descubrir
    referencias sin FK declarada. Cubre el caso de mayor riesgo: una ReteIVA cuyo id deje de
    coincidir con el de SIIGO rompe la contabilización real con `The id doesn't exist`.
    """

    def test_una_fila_local_adopta_el_id_de_siigo_y_reapunta_document_taxes(self, engine, session):
        from app.infrastructure.persistence.repositories.retention_repository import (
            RetentionRepository,
        )

        # Fila "local" (nacida sin id de SIIGO, p. ej. de una corrida de backfill con
        # colisión) con un documento apuntándole.
        session.execute(
            text(
                "INSERT INTO integration_retentions (id, name, type, percentage, active) "
                "VALUES (1, 'ReteIVA 15%', 'reteiva', 15.0, true)"
            )
        )
        session.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (99, 1, 500)")
        )
        session.commit()

        RetentionRepository(session).upsert_siigo_many(
            [{"id": 10608, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0}]
        )

        assert session.execute(
            text("SELECT id FROM integration_retentions WHERE id = 1")
        ).first() is None
        assert (
            session.execute(text("SELECT id FROM integration_retentions WHERE id = 10608")).scalar()
            == 10608
        )
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 99")
            ).scalar()
            == 10608
        )
