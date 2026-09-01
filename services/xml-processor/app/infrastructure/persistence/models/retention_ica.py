from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint

from app.infrastructure.config.database import Base

#: Concepto con el que se guarda una tarifa que aplica a toda la operación, sin distinguir
#: actividad. Es el valor por defecto cuando el archivo importado no trae columna de
#: concepto, de modo que una tabla antigua sigue siendo válida.
CONCEPTO_GENERAL = "todos"


class RetentionIcaRate(Base):
    """Tarifa de ReteICA de un municipio para un concepto de operación.

    La clave es **(municipio, concepto)** y no solo el municipio. Según el contador, «el
    cálculo de la retención está dado por concepto: compra, servicios, honorarios,
    comisiones, servicios profesionales», y en Bogotá cada actividad tiene su banda. Un
    municipio con una sola tarifa obligaba a elegir entre aplicar la misma a todo —retener de
    más o de menos según el caso— o no proponer ReteICA en absoluto.

    Es la misma estructura que `retention_fuente_rates`, donde la tarifa depende del par
    (concepto, tipo de contribuyente). La diferencia es qué la determina: allí el concepto y
    el régimen del tercero; aquí el concepto y el municipio.
    """

    __tablename__ = "retention_ica_rates"
    __table_args__ = (
        UniqueConstraint(
            "municipality_code",
            "retention_concept",
            name="uq_retention_ica_municipality_concept",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    municipality_code = Column(String(20), nullable=False, index=True)  # DANE u otro
    municipality_name = Column(String(120), nullable=True)
    #: Concepto de la operación que fija la tarifa: 'servicios', 'compras', 'honorarios',
    #: 'comisiones', 'servicios profesionales'… Se guarda tal como lo escribe el contador en
    #: la plantilla, normalizado a minúsculas, porque es él quien conoce la nomenclatura de
    #: su municipio. `todos` significa que la tarifa aplica a cualquier concepto.
    retention_concept = Column(
        String(120), nullable=False, default=CONCEPTO_GENERAL, server_default=CONCEPTO_GENERAL
    )
    #: Tarifa del municipio, en la MISMA unidad en que la trae el catálogo de Impuestos.
    #:
    #: El ICA se publica tradicionalmente por mil (Bogotá servicios: 9,66 por mil), y SIIGO
    #: sincroniza esa cifra tal cual — «ReteICA 9.66»—. El catálogo manda: aquí se escribe el
    #: mismo número, 9.66, no su equivalente 0.966. Tenerlo en dos unidades no es un detalle
    #: de formato: la sugerencia calcula `base × tarifa / 100`, así que confundirlas retiene
    #: diez veces de más o de menos sobre dinero de un tercero.
    #:
    #: La validación de RF-08 compara esta tarifa con la del catálogo y, si difieren por un
    #: factor de diez exacto, se niega a proponer la retención y nombra la discrepancia en vez
    #: de elegir una de las dos por su cuenta
    #: (`llm-service · domain/services/retention_validation.py`).
    percentage = Column(Numeric(10, 6), nullable=False)
    #: Base mínima en UVT por debajo de la cual NO se practica la retención.
    #:
    #: Va en la tabla, y no fija en el código, porque el ICA es un impuesto **territorial**:
    #: cada municipio fija su propio tope y no hay uniformidad nacional. Bogotá pide 4 UVT en
    #: servicios y 27 en compras; Cali 3 y 15; Bucaramanga 25 y 50; Medellín 15 para cualquier
    #: operación. Con un valor fijo de Bogotá, contabilizar en Bucaramanga proponía ReteICA
    #: sobre facturas que no la causan —retener dinero que no corresponde— en todo el rango
    #: entre 4 y 25 UVT.
    #:
    #: Se guarda en UVT y no en pesos a propósito: la UVT la actualiza la DIAN cada año, así
    #: que un importe en pesos caduca cada enero sin que nada lo señale. La conversión se hace
    #: al construir el prompt, con la UVT del año del documento.
    #:
    #: `NULL` = el municipio no fija tope para ese concepto (toda operación retiene).
    minimum_base_uvt = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
