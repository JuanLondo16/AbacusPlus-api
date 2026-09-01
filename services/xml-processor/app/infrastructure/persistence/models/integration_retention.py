from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.infrastructure.config.database import Base


class IntegrationRetention(Base):
    """Stub local de `integration_retentions` — tabla gestionada por integration-config-service.

    Mismo patrón que `IntegrationTax`/`integration_taxes`: xml-processor solo LEE. Fusiona lo
    que antes vivía partido entre `integration_taxes` (retenciones sin municipio) y
    `retention_ica_rates` (ReteICA por municipio, solo en este servicio) — cada fila `type=
    'reteica'` ya trae el municipio, el concepto y la base mínima, así que no hace falta
    cruzarla con ninguna otra tabla para saber si es una tarifa válida.
    """

    __tablename__ = "integration_retentions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    #: Normalizado en origen: 'retefuente' | 'reteica' | 'reteiva' | 'autorretencion'.
    type = Column(String(50), nullable=False)
    percentage = Column(Numeric(10, 6), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    municipality_code = Column(String(20), nullable=True)
    municipality_name = Column(String(120), nullable=True)
    retention_concept = Column(String(120), nullable=True)
    minimum_base_uvt = Column(Numeric(10, 2), nullable=True)
