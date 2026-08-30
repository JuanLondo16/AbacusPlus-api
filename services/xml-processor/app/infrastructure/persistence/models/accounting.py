"""RF-05: persistencia de la cola de contabilización y de su auditoría.

Tres tablas con responsabilidades separadas y que no se solapan:

- `accounting_jobs` — el **estado vivo** de la cola. Una fila por documento encolado. Es
  mutable: avanza de pendiente a en curso, acumula intentos, se reprograma.
- `accounting_attempts` — el **historial**. Una fila por intento contra SIIGO, y **nunca se
  modifica ni se borra**. Es lo que permite responder «¿qué se le envió exactamente a SIIGO
  el martes a las 3 y qué contestó?» meses después.
- `document_field_changes` — las **correcciones humanas**. Quién cambió qué campo, de qué
  valor a cuál. Cierra la trazabilidad del ciclo «Error → Editar → Reintentar»: sin ella, un
  documento contabilizado tras una corrección no deja constancia de qué se corrigió.

Por qué la cola está en base de datos y no en memoria
-----------------------------------------------------
Porque un reinicio del proceso no puede perder el rastro de un documento que ya se envió a
SIIGO. Una cola en memoria, ante un despliegue a mitad de lote, deja documentos cuyo
desenlace nadie conoce y sin ninguna fila que lo diga — y un documento así solo se puede
resolver reenviándolo (duplicando) o revisándolo a mano uno por uno. Con la cola persistida,
el trabajo sobrevive al reinicio con su cerrojo puesto y su historial intacto.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.config.database import Base

#: JSON portable: JSONB en PostgreSQL, JSON genérico en el resto.
#:
#: JSONB a secas no compila en SQLite, que es lo que usan los tests de este servicio. La
#: variante conserva JSONB donde importa —producción, donde permite indexar y consultar
#: dentro del cuerpo guardado— sin obligar a que la suite entera necesite PostgreSQL para
#: correr, que la haría mucho más lenta y más frágil.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class JobState:
    """Estado **interno** de un trabajo de la cola.

    No confundir con `DocumentStatus`: son dos ejes distintos y mezclarlos fue justamente lo
    que hizo aparecer un sexto estado funcional. El documento tiene cinco estados de negocio;
    el trabajo tiene los suyos, que son un detalle de implementación y no se muestran como
    estado del documento en ninguna parte de la interfaz.
    """

    #: Esperando a que un worker lo tome. Incluye los que aguardan su backoff.
    PENDING = "PENDING"
    #: Tomado por un worker, con la llamada a SIIGO en curso.
    RUNNING = "RUNNING"
    #: Contabilizado con éxito. Terminal.
    SUCCEEDED = "SUCCEEDED"
    #: Falló y no se reintentará solo. El documento queda en ERROR con su acción recomendada.
    FAILED = "FAILED"
    #: Desenlace desconocido: hay que preguntarle a SIIGO qué pasó antes de tocar nada.
    #: Terminal para la cola — solo la reconciliación humana lo saca de aquí.
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    #: Cancelado por un usuario antes de enviarse.
    CANCELLED = "CANCELLED"

    #: Estados desde los que un worker todavía puede actuar.
    ACTIVE = frozenset({PENDING, RUNNING})
    #: Estados en los que el trabajo ya no avanza solo.
    TERMINAL = frozenset({SUCCEEDED, FAILED, NEEDS_RECONCILIATION, CANCELLED})


class AccountingJob(Base):
    """Un documento encolado para contabilizar.

    La unicidad la impone un índice parcial en base de datos (ver `tenant_migrations`): un
    documento no puede tener dos trabajos activos a la vez. Es la segunda barrera contra el
    doble envío, después del cerrojo del propio documento, y la única que sigue en pie si
    alguna vez hubiera varias réplicas del servicio.
    """

    __tablename__ = "accounting_jobs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    #: Agrupa los trabajos encolados en un mismo envío, para poder mostrar el progreso del
    #: lote sin que el frontend tenga que llevar la lista de ids.
    batch_id = Column(String(64), nullable=True, index=True)

    state = Column(String(30), nullable=False, default=JobState.PENDING, index=True)

    #: Intentos ya consumidos. El primer envío es el intento 1.
    attempt = Column(Integer, nullable=False, server_default=text("0"), default=0)
    #: Copiado de la configuración al encolar, no leído del entorno al reintentar. Así, subir
    #: el máximo global no revive trabajos que ya se dieron por agotados con la regla vieja.
    max_attempts = Column(Integer, nullable=False, server_default=text("5"), default=5)

    #: Momento a partir del cual el trabajo puede tomarse. Es el backoff: un worker nunca
    #: toma un trabajo cuyo `next_attempt_at` esté en el futuro.
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)

    #: Última clasificación conocida. Decide si el trabajo se reprograma o se detiene.
    error_class = Column(String(30), nullable=True)
    recommended_action = Column(String(40), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_code = Column(String(60), nullable=True)
    last_http_status = Column(Integer, nullable=True)

    #: Identificador del comprobante en SIIGO, cuando se llega a conocer.
    siigo_id = Column(String(120), nullable=True)
    siigo_name = Column(String(120), nullable=True)

    #: Quién lo encoló. Necesario para la auditoría y para notificar al usuario correcto.
    enqueued_by = Column(String(120), nullable=True)

    #: Identificador del worker que lo tiene tomado. Permite detectar trabajos huérfanos
    #: —tomados por un proceso que murió— sin confundirlos con trabajos en curso legítimos.
    locked_by = Column(String(120), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # El índice que sostiene la consulta del worker: «dame el siguiente pendiente cuyo
        # backoff ya venció». Sin él, cada ciclo del worker escanea la tabla entera.
        Index("ix_accounting_jobs_pickup", "state", "next_attempt_at"),
    )


class AccountingAttempt(Base):
    """Un intento de contabilización contra SIIGO. Append-only: nunca se actualiza ni se borra.

    Es la memoria del sistema. Cuando un cliente pregunta por qué una factura quedó
    duplicada, o por qué un documento lleva tres días sin contabilizarse, la respuesta está
    aquí y en ningún otro sitio: qué se envió, qué contestó SIIGO, con qué código HTTP, en
    qué intento y a qué hora.

    Guarda el request y la response completos en JSONB en lugar de un resumen, porque el
    campo que hará falta para entender un caso raro es siempre el que no se guardó.
    """

    __tablename__ = "accounting_attempts"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("accounting_jobs.id"), nullable=True, index=True)

    #: Número de intento dentro del trabajo. Empieza en 1.
    attempt = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    #: Cuerpo enviado a SIIGO. Es la causación exacta de ese intento — no la actual, que pudo
    #: haberse corregido después. Sin esta foto, un documento corregido tres veces no permite
    #: saber cuál de las tres versiones fue la que SIIGO rechazó.
    request_payload = Column(_JSON, nullable=True)
    response_body = Column(_JSON, nullable=True)
    http_status = Column(Integer, nullable=True)

    ok = Column(Boolean, nullable=False, default=False)
    siigo_id = Column(String(120), nullable=True)
    siigo_name = Column(String(120), nullable=True)

    error_message = Column(Text, nullable=True)
    error_code = Column(String(60), nullable=True)
    error_class = Column(String(30), nullable=True)
    recommended_action = Column(String(40), nullable=True)

    #: Quién provocó el intento: el usuario que lo encoló, o 'worker' si fue un reintento
    #: automático. Distinguirlos es lo que permite auditar si un duplicado lo causó una
    #: persona o una política de reintento.
    triggered_by = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_accounting_attempts_doc_created", "document_id", "created_at"),
    )


class DocumentFieldChange(Base):
    """Corrección manual de un campo de la causación. Append-only.

    Existe por el flujo «Error → Editar → Reintentar». Si un documento se contabiliza tras
    una corrección, la evidencia de qué se corrigió no puede vivir solo en el valor actual
    del campo: eso muestra el resultado, no el cambio. Para una auditoría contable la
    pregunta es siempre «¿quién cambió esta cuenta PUC, cuándo y desde qué valor?».
    """

    __tablename__ = "document_field_changes"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    #: Entidad y fila concretas: 'document', 'document_detail', 'document_tax'.
    entity = Column(String(40), nullable=False)
    #: Id de la fila afectada cuando no es el documento en sí (p. ej. la línea de detalle).
    entity_id = Column(Integer, nullable=True)
    field = Column(String(60), nullable=False)

    #: Se guardan como texto y no con el tipo original a propósito: la tabla debe servir para
    #: cualquier campo, y un histórico de auditoría se lee, no se opera.
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    changed_by = Column(String(120), nullable=True)
    #: Contexto del cambio: 'error_correction' cuando se corrige un documento en ERROR.
    reason = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_document_field_changes_doc_created", "document_id", "created_at"),
    )
