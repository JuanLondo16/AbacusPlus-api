"""Reidentificación del catálogo de impuestos con los ids de SIIGO.

Estas pruebas necesitan PostgreSQL de verdad, no SQLite: lo que se está comprobando es que
una clave ajena se reapunta sin romperse y que la secuencia queda por encima del mayor id.
Ninguna de las dos cosas existe en SQLite, así que probarlo ahí demostraría poco.

El caso que reproducen es el que ocurrió en producción: `ReteIVA 15%` guardado con la clave
local 15 mientras en SIIGO es 10608, y un documento apuntando a esa clave. Al contabilizar,
el 15 viajaba a SIIGO como si fuera suyo y respondía `The id doesn't exist: 15`.
"""

import os

import pytest
from app.infrastructure.persistence.repositories.tax_repository import (
    TaxRepository,
    _normalizar,
)
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

CREATE TABLE document_taxes (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER REFERENCES integration_taxes(id),
    value NUMERIC(18,2)
);

CREATE TABLE document_details (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER REFERENCES integration_taxes(id)
);
"""


@pytest.fixture
def session():
    try:
        engine = create_engine(_URL)
        with engine.begin() as conexion:
            for sentencia in filter(None, (s.strip() for s in _ESQUEMA.split(";"))):
                conexion.execute(text(sentencia))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL de pruebas no disponible: {exc}")

    fabrica = sessionmaker(bind=engine)
    sesion = fabrica()
    yield sesion
    sesion.close()
    engine.dispose()


def _sembrar_catalogo_heredado(session) -> None:
    """El estado real encontrado en el cliente: ids de la secuencia local, 1..n."""
    session.execute(
        text(
            "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
            "(4, 'Retefuente 10%', 'Retefuente', 10.0, true),"
            "(15, 'ReteIVA 15%', 'ReteIVA', 15.0, true),"
            "(16, 'Impoconsumo 8%', 'Impoconsumo', 8.0, true)"
        )
    )
    session.execute(
        text(
            "INSERT INTO document_taxes (document_id, tax_id, value) VALUES "
            "(27, 15, 641.11), (28, 16, 8964.21)"
        )
    )
    session.execute(text("INSERT INTO document_details (document_id, tax_id) VALUES (27, 15)"))
    session.commit()


_CATALOGO_SIIGO = [
    {"id": 10608, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0, "active": True},
    {
        "id": 10771,
        "name": "Impoconsumo 8%",
        "type": "Impoconsumo",
        "percentage": 8.0,
        "active": True,
    },
    {
        "id": 10402,
        "name": "Retefuente 10%",
        "type": "Retefuente",
        "percentage": 10.0,
        "active": True,
    },
]


class TestReidentificacion:
    def test_la_fila_heredada_adopta_el_id_de_siigo(self, session):
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        ids = {
            fila[0]: fila[1]
            for fila in session.execute(text("SELECT name, id FROM integration_taxes")).fetchall()
        }
        assert ids["ReteIVA 15%"] == 10608
        assert ids["Impoconsumo 8%"] == 10771

    def test_las_claves_locales_desaparecen(self, session):
        """Mientras exista la fila 15, algo puede volver a enviarla a SIIGO."""
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        restantes = session.execute(
            text("SELECT id FROM integration_taxes WHERE id IN (4, 15, 16)")
        ).fetchall()
        assert restantes == []

    def test_los_documentos_quedan_apuntando_al_id_de_siigo(self, session):
        """Lo que de verdad importa: la retención del documento 27 ya no es la 15."""
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 27")
            ).scalar()
            == 10608
        )
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 28")
            ).scalar()
            == 10771
        )

    def test_tambien_se_reapuntan_los_detalles(self, session):
        """`document_details.tax_id` cita la misma tabla y se descubre por catálogo."""
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_details WHERE document_id = 27")
            ).scalar()
            == 10608
        )

    def test_no_se_pierde_ninguna_referencia(self, session):
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        huerfanas = session.execute(
            text(
                "SELECT count(*) FROM document_taxes d "
                "LEFT JOIN integration_taxes t ON t.id = d.tax_id "
                "WHERE d.tax_id IS NOT NULL AND t.id IS NULL"
            )
        ).scalar()
        assert huerfanas == 0

    def test_repetir_la_sincronizacion_no_cambia_nada(self, session):
        """Debe ser idempotente: el contador la ejecutará más de una vez."""
        _sembrar_catalogo_heredado(session)
        repositorio = TaxRepository(session)

        repositorio.upsert_many(_CATALOGO_SIIGO)
        repositorio.upsert_many(_CATALOGO_SIIGO)

        filas = session.execute(text("SELECT id FROM integration_taxes ORDER BY id")).fetchall()
        assert [fila[0] for fila in filas] == [10402, 10608, 10771]
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 27")
            ).scalar()
            == 10608
        )

    def test_el_nombre_reescrito_por_una_importacion_previa_tambien_empareja(self, session):
        """«ReteIVA 15%.» y «ReteIVA 15%» son la misma fila importada dos veces."""
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) "
                "VALUES (30, 'ReteIVA 15%.', 'ReteIVA', 15.0, true)"
            )
        )
        session.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (40, 30, 10)")
        )
        session.commit()

        TaxRepository(session).upsert_many([_CATALOGO_SIIGO[0]])

        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 40")
            ).scalar()
            == 10608
        )

    def test_una_fila_que_ya_tiene_id_de_siigo_no_se_toca(self, session):
        """Reidentificar una fila correcta reapuntaría documentos a otro impuesto."""
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
                "(10608, 'ReteIVA 15%', 'ReteIVA', 15.0, true),"
                "(10771, 'Impoconsumo 8%', 'Impoconsumo', 8.0, true)"
            )
        )
        session.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (50, 10608, 1)")
        )
        session.commit()

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 50")
            ).scalar()
            == 10608
        )

    def test_la_secuencia_queda_por_encima_del_mayor_id(self, session):
        """Si no, la siguiente fila local nacería con un id que SIIGO ya usa."""
        _sembrar_catalogo_heredado(session)

        TaxRepository(session).upsert_many(_CATALOGO_SIIGO)

        session.execute(
            text(
                "INSERT INTO integration_taxes (name, type, percentage, active) "
                "VALUES ('Impuesto local nuevo', 'Otro', 1.0, true)"
            )
        )
        session.commit()

        nuevo = session.execute(
            text("SELECT id FROM integration_taxes WHERE name = 'Impuesto local nuevo'")
        ).scalar()
        assert nuevo > 10771


class TestNormalizacionDeNombres:
    @pytest.mark.parametrize(
        "izquierda,derecha",
        [
            ("ReteIVA 15%", "ReteIVA 15%."),
            ("autorretencion", "autorretención."),
            ("IVA  19%", "iva 19%"),
        ],
    )
    def test_variantes_de_la_misma_fila_normalizan_igual(self, izquierda, derecha):
        assert _normalizar(izquierda) == _normalizar(derecha)

    def test_impuestos_distintos_no_colisionan(self):
        assert _normalizar("IVA 19%") != _normalizar("IVA 5%")


_ESQUEMA_SIN_FK = """
DROP TABLE IF EXISTS document_taxes;
DROP TABLE IF EXISTS document_details;
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

CREATE TABLE document_taxes (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER NOT NULL,
    value DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE document_details (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    tax_id INTEGER
);
"""


@pytest.fixture
def session_sin_fk():
    """El esquema tal y como está en la base del cliente: `tax_id` sin clave ajena."""
    try:
        engine = create_engine(_URL)
        with engine.begin() as conexion:
            for sentencia in filter(None, (s.strip() for s in _ESQUEMA_SIN_FK.split(";"))):
                conexion.execute(text(sentencia))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL de pruebas no disponible: {exc}")

    fabrica = sessionmaker(bind=engine)
    sesion = fabrica()
    yield sesion
    sesion.close()
    engine.dispose()


class TestReferenciasSinClaveAjena:
    """El esquema real no declara la clave ajena de `document_taxes.tax_id`.

    Descubrir las referencias solo por el catálogo de claves ajenas no encuentra ninguna, y
    la reidentificación borraría la fila vieja dejando los documentos apuntando a un impuesto
    inexistente. Este es el caso que obliga a buscar también por nombre de columna.
    """

    def test_se_reapuntan_aunque_no_haya_clave_ajena(self, session_sin_fk):
        session_sin_fk.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) "
                "VALUES (15, 'ReteIVA 15%', 'ReteIVA', 15.0, true)"
            )
        )
        session_sin_fk.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (27, 15, 641.11)")
        )
        session_sin_fk.execute(
            text("INSERT INTO document_details (document_id, tax_id) VALUES (27, 15)")
        )
        session_sin_fk.commit()

        TaxRepository(session_sin_fk).upsert_many([_CATALOGO_SIIGO[0]])

        assert (
            session_sin_fk.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 27")
            ).scalar()
            == 10608
        )
        assert (
            session_sin_fk.execute(
                text("SELECT tax_id FROM document_details WHERE document_id = 27")
            ).scalar()
            == 10608
        )

    def test_no_queda_ninguna_referencia_apuntando_a_la_clave_local(self, session_sin_fk):
        """Sin clave ajena nadie avisa: hay que comprobarlo explícitamente."""
        session_sin_fk.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) "
                "VALUES (15, 'ReteIVA 15%', 'ReteIVA', 15.0, true)"
            )
        )
        session_sin_fk.execute(
            text("INSERT INTO document_taxes (document_id, tax_id, value) VALUES (27, 15, 641.11)")
        )
        session_sin_fk.commit()

        TaxRepository(session_sin_fk).upsert_many([_CATALOGO_SIIGO[0]])

        huerfanas = session_sin_fk.execute(
            text(
                "SELECT count(*) FROM document_taxes d "
                "LEFT JOIN integration_taxes t ON t.id = d.tax_id WHERE t.id IS NULL"
            )
        ).scalar()
        assert huerfanas == 0

    def test_la_tabla_de_impuestos_no_se_reapunta_a_si_misma(self, session_sin_fk):
        """`integration_taxes` se excluye del barrido por nombre de columna."""
        referencias = TaxRepository(session_sin_fk)._referencias()

        assert ("integration_taxes", "tax_id") not in referencias
        assert ("document_taxes", "tax_id") in referencias
        assert ("document_details", "tax_id") in referencias


class TestVariosImpuestosConElMismoPorcentaje:
    """El catálogo real tiene cinco impuestos al 19%.

    Con una sola pasada, un impuesto de SIIGO reclamaba por porcentaje la fila que le
    correspondía por nombre a otro; el siguiente chocaba contra el `UNIQUE(name)` y abortaba
    la sincronización entera con `duplicate key value violates unique constraint`. Ocurrió al
    ejecutarla contra la base real.
    """

    def _sembrar_los_cinco(self, session):
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
                "(1,  'IVA 19%',            'IVA', 19.0, false),"
                "(26, 'Iva servicios 19%',  'IVA', 19.0, false),"
                "(28, 'IVA 19%.',           'IVA', 19.0, true),"
                "(31, 'Iva servicios 19%.', 'IVA', 19.0, true),"
                "(32, 'Iva Exterior 19%',   'IVA', 19.0, true)"
            )
        )
        session.execute(
            text("INSERT INTO document_details (document_id, tax_id) VALUES (60, 1), (61, 32)")
        )
        session.commit()

    _CINCO_EN_SIIGO = [
        {"id": 10594, "name": "IVA 19%", "type": "IVA", "percentage": 19.0, "active": False},
        {
            "id": 10595,
            "name": "Iva servicios 19%",
            "type": "IVA",
            "percentage": 19.0,
            "active": True,
        },
        {
            "id": 10596,
            "name": "Iva Exterior 19%",
            "type": "IVA",
            "percentage": 19.0,
            "active": True,
        },
    ]

    def test_la_sincronizacion_no_revienta_por_nombre_duplicado(self, session):
        self._sembrar_los_cinco(session)

        TaxRepository(session).upsert_many(self._CINCO_EN_SIIGO)

        assert (
            session.execute(
                text("SELECT count(*) FROM integration_taxes WHERE id IN (10594, 10595, 10596)")
            ).scalar()
            == 3
        )

    def test_cada_impuesto_toma_la_fila_de_su_nombre(self, session):
        """«IVA 19%» debe adoptar 10594, no la fila de «Iva Exterior 19%»."""
        self._sembrar_los_cinco(session)

        TaxRepository(session).upsert_many(self._CINCO_EN_SIIGO)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_details WHERE document_id = 60")
            ).scalar()
            == 10594
        )
        assert (
            session.execute(
                text("SELECT tax_id FROM document_details WHERE document_id = 61")
            ).scalar()
            == 10596
        )

    def test_la_fila_local_sobrante_se_aparta_pero_no_se_borra(self, session):
        """Puede tener documentos apuntando a ella: se delata, no se elimina."""
        self._sembrar_los_cinco(session)

        TaxRepository(session).upsert_many(self._CINCO_EN_SIIGO)

        sobrantes = session.execute(
            text("SELECT id, name FROM integration_taxes WHERE id IN (28, 31)")
        ).fetchall()
        assert len(sobrantes) == 2
        assert all("local" in fila[1] for fila in sobrantes)


class TestNombresQueSoloSeDiferencianEnLaPuntuacion:
    """El catálogo real trae parejas «X» y «X.»: son impuestos DISTINTOS en SIIGO.

    Normalizando, ambos nombres colapsan en el mismo, así que emparejar primero por el
    nombre normalizado dejaba que «IVA 19%» se llevara la fila de «IVA 19%.». El cruce no
    perdía datos, pero al escribir el nombre definitivo chocaba con la fila aún sin procesar
    y abortaba la sincronización entera:
    `duplicate key value violates unique constraint "integration_taxes_name_key"`.

    Ocurrió dos veces contra la base real antes de anteponer el emparejamiento exacto.
    """

    _PAREJAS_EN_SIIGO = [
        {"id": 10594, "name": "IVA 19%", "type": "IVA", "percentage": 19.0, "active": True},
        {"id": 20921, "name": "IVA 19%.", "type": "IVA", "percentage": 19.0, "active": True},
        {"id": 10608, "name": "ReteIVA 15%", "type": "ReteIVA", "percentage": 15.0, "active": True},
        {
            "id": 20923,
            "name": "ReteIVA 15%.",
            "type": "ReteIVA",
            "percentage": 15.0,
            "active": True,
        },
    ]

    def _sembrar(self, session):
        session.execute(
            text(
                "INSERT INTO integration_taxes (id, name, type, percentage, active) VALUES "
                "(1,  'IVA 19%',      'IVA',     19.0, true),"
                "(28, 'IVA 19%.',     'IVA',     19.0, true),"
                "(15, 'ReteIVA 15%',  'ReteIVA', 15.0, true),"
                "(30, 'ReteIVA 15%.', 'ReteIVA', 15.0, true)"
            )
        )
        session.execute(
            text(
                "INSERT INTO document_taxes (document_id, tax_id, value) VALUES "
                "(70, 15, 100), (71, 30, 200)"
            )
        )
        session.commit()

    def test_la_sincronizacion_completa_sin_chocar(self, session):
        self._sembrar(session)

        assert TaxRepository(session).upsert_many(self._PAREJAS_EN_SIIGO) == 4

    def test_cada_variante_conserva_su_propia_identidad(self, session):
        """«ReteIVA 15%» es 10608 y «ReteIVA 15%.» es 20923: no se pueden cruzar."""
        self._sembrar(session)

        TaxRepository(session).upsert_many(self._PAREJAS_EN_SIIGO)

        ids = dict(session.execute(text("SELECT name, id FROM integration_taxes")).fetchall())
        assert ids["IVA 19%"] == 10594
        assert ids["IVA 19%."] == 20921
        assert ids["ReteIVA 15%"] == 10608
        assert ids["ReteIVA 15%."] == 20923

    def test_los_documentos_siguen_a_su_impuesto_y_no_al_de_al_lado(self, session):
        self._sembrar(session)

        TaxRepository(session).upsert_many(self._PAREJAS_EN_SIIGO)

        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 70")
            ).scalar()
            == 10608
        )
        assert (
            session.execute(
                text("SELECT tax_id FROM document_taxes WHERE document_id = 71")
            ).scalar()
            == 20923
        )
