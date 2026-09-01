from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.infrastructure.config.database import Base


class RetentionCriterion(Base):
    """RF-08 · Un criterio del contador sobre cómo determinar las retenciones.

    Son las respuestas del contador del cliente a preguntas como «¿cómo determina la tarifa
    de ReteICA?» o «¿qué condiciones impiden practicar ReteFuente?». Alimentan el prompt de
    la sugerencia automática como fuente ORIENTATIVA: pesan más que una deducción del modelo
    y menos que una tarifa oficial cargada.

    **Por qué son datos por cliente y no una constante del código.** Cada empresa tiene su
    contador, su régimen y sus criterios, y esos criterios cambian —por una reforma, por un
    concepto de la DIAN o porque el contador afina su interpretación—. Como constante se
    aplicarían los criterios de un cliente a todos los demás, y cambiarlos exigiría un
    despliegue. Viven en la base de cada tenant, igual que su perfil fiscal.

    **Por qué NO se indexan en el RAG.** Se cargan TODOS y entran SIEMPRE al prompt. El
    índice vectorial recupera por parecido, que es probabilístico: un criterio que gobierna
    cada decisión no puede depender de que un embedding acierte en traerlo. El RAG guarda lo
    que sí es masivo y variable —los casos contabilizados—; esto es un puñado de reglas
    estables que aplican a todas las facturas.
    """

    __tablename__ = "retention_criteria"

    id = Column(Integer, primary_key=True)
    #: Retención a la que aplica: 'retefuente' | 'reteica' | 'reteiva' | 'autorretencion'
    #: | 'proceso'. Los de 'proceso' gobiernan la decisión completa y entran siempre; los
    #: demás solo cuando esa retención es candidata, para no gastar contexto en reglas de
    #: retenciones ya descartadas.
    tema = Column(String(30), nullable=False, index=True)
    #: La pregunta que originó el criterio. Se conserva porque un criterio suelto pierde su
    #: alcance: «por el municipio» solo significa algo junto a «¿cómo se determina si aplica
    #: ReteICA?». Además permite contrastarlo con el cuestionario original al revisarlo.
    pregunta = Column(Text, nullable=False)
    #: La respuesta del contador, tal como la dio.
    criterio = Column(Text, nullable=False)
    #: Permite retirar un criterio sin borrarlo, conservando el rastro de que existió.
    activo = Column(Boolean, nullable=False, default=True)
    #: Origen del criterio, para auditarlo: qué documento o conversación lo sustenta.
    fuente = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
