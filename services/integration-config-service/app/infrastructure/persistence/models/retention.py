from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, func, text

from app.infrastructure.config.database import Base


class Retention(Base):
    """`integration_retentions`: ReteICA, ReteIVA, Retefuente y Autorretención.

    Separada de `integration_taxes` (que ahora solo guarda impuestos reales del documento:
    IVA, Impoconsumo, AdValorem). Antes las retenciones vivían mezcladas ahí, distinguidas
    solo por `type`, y el ReteICA por municipio vivía ADEMÁS en una tabla paralela del
    xml-processor (`retention_ica_rates`) que casi nunca coincidía en porcentaje con las 5
    tarifas genéricas sincronizadas de SIIGO — el pipeline de sugerencia por IA dependía de
    ese emparejamiento por porcentaje exacto para poder proponer un ReteICA, y sin
    coincidencia la sugerencia se descartaba aunque la tarifa real (con municipio correcto)
    existiera.

    Esta tabla fusiona ambas cosas: cada fila es una opción COMPLETA y autosuficiente. Para
    `type='reteica'` trae además el municipio, el concepto y la base mínima que antes sólo
    vivían en `retention_ica_rates`; para las demás (`retefuente`, `reteiva`,
    `autorretencion`) las columnas de municipio quedan NULL, igual que hoy en
    `integration_taxes`. Elegir un `id` de esta tabla ya implica una tarifa, un municipio (si
    aplica) y una base mínima consistentes entre sí — no hay una segunda tabla con la que
    pueda discrepar.

    Mismo patrón arquitectónico que `Tax`/`integration_taxes`: la posee este servicio;
    xml-processor y llm-service mantienen su propio stub de solo lectura.
    """

    __tablename__ = "integration_retentions"
    __table_args__ = (
        # Único criterio de identidad de una fila de ReteICA: (municipio, concepto). Es EL
        # MISMO criterio que ya tenía `retention_ica_rates` — un municipio trae una fila por
        # concepto (servicios, compras, honorarios…) porque la tarifa la fija la actividad.
        # `name` no sirve de clave aquí: se sintetiza para mostrarlo en el selector
        # ("ReteICA Bogotá D.C. · servicios"), pero dos municipios distintos podrían generar
        # nombres iguales por coincidencia y NO son la misma fila.
        Index(
            "uq_integration_retentions_ica_municipio_concepto",
            "municipality_code",
            "retention_concept",
            unique=True,
            postgresql_where=text("type = 'reteica'"),
            sqlite_where=text("type = 'reteica'"),
        ),
        # Para lo demás (retefuente/reteiva/autorretencion, sincronizadas de SIIGO o cargadas
        # a mano) se conserva el criterio que ya usaba `integration_taxes.name` — son filas
        # sin municipio, y el nombre ("ReteIVA 15%") es la identidad natural, igual que hoy.
        Index(
            "uq_integration_retentions_name",
            "name",
            unique=True,
            postgresql_where=text("type <> 'reteica'"),
            sqlite_where=text("type <> 'reteica'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    #: Nombre para mostrar. Para retefuente/reteiva/autorretencion es el que trae SIIGO o el
    #: Excel ("ReteIVA 15%"). Para reteica se sintetiza al importar ("ReteICA Bogotá D.C. ·
    #: servicios"): no hay un nombre "natural" por fila, la identidad es (municipio, concepto).
    name = Column(String(150), nullable=False)
    #: 'retefuente' | 'reteica' | 'reteiva' | 'autorretencion' (o la grafía que traiga SIIGO:
    #: 'Retefuente', 'ReteICA'... se normaliza al clasificar, no al guardar, igual que hoy
    #: hace `integration_taxes.type`).
    type = Column(String(50), nullable=False, index=True)
    #: Igual que `retention_ica_rates.percentage`: NUMERIC(10,6) y no (10,4) como
    #: `integration_taxes`, porque el ICA se publica por mil con hasta 6 decimales
    #: (9.660000) y esta tabla ahora también guarda esas filas.
    percentage = Column(Numeric(10, 6), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    #: Código DANE del municipio. NULL salvo en filas `reteica`.
    municipality_code = Column(String(20), nullable=True, index=True)
    municipality_name = Column(String(120), nullable=True)
    #: Concepto de la operación que fija la tarifa dentro del municipio ('servicios',
    #: 'compras', 'honorarios'…, o 'todos'). NULL salvo en filas `reteica`.
    retention_concept = Column(String(120), nullable=True)
    #: Base mínima en UVT por debajo de la cual NO se practica la retención. Solo tiene
    #: sentido para `reteica` (el ICA es territorial y cada municipio fija su propio tope);
    #: NULL en las demás filas.
    minimum_base_uvt = Column(Numeric(10, 2), nullable=True)
    #: De dónde llegó la fila: 'siigo' (sync), 'excel' (import de municipios ICA),
    #: 'migracion_integration_taxes' / 'migracion_retention_ica_rates' (backfill único del
    #: 2026-08-31). Es diagnóstico, no gobierna ninguna regla — ayuda a auditar por qué existe
    #: una fila concreta sin tener que consultar el historial de despliegues.
    source = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
