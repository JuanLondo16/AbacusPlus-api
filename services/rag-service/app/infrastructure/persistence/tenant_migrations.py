"""Migraciones de la base de cada cliente para el rag-service.

Mismo criterio que el archivo homónimo del xml-processor: una sola lista, sentencias
idempotentes y aditivas, ejecutadas en cada arranque y en cada aprovisionamiento. Hasta
ahora este servicio solo creaba la tabla con `create_all`, que no toca las bases existentes:
una columna nueva en `document_chunks` habría dejado a los clientes ya aprovisionados con el
esquema viejo y el fallo habría aparecido en tiempo de consulta.

Cómo añadir una migración: al final de la tupla, idempotente (`IF NOT EXISTS`), y sin romper
la versión anterior del servicio que siga corriendo durante el despliegue.
"""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

TENANT_MIGRATIONS: tuple[str, ...] = (
    # RF-08: solo el conocimiento de causaciones efectivamente contabilizadas en SIIGO es
    # reutilizable. Los chunks anteriores a esta migración se indexaron al procesar o al
    # aprobar, sin garantía de haber llegado a SIIGO, así que quedan como NO validados: no
    # se borran (siguen sirviendo de contexto documental) pero dejan de ser precedente
    # contable. El backfill `/internal/documents/reindex` del xml-processor los repone a
    # partir de los documentos que sí están en «Contabilizada».
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS is_validated BOOLEAN "
    "NOT NULL DEFAULT FALSE",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS siigo_id VARCHAR(100)",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_source "
    "ON document_chunks (source_type, source_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_is_validated "
    "ON document_chunks (is_validated)",
    # RF-08 · búsqueda híbrida: rasgos estructurados del caso contabilizado (NIT del emisor,
    # municipio, cuentas, tipos de retención). Permiten filtrar por lo que de verdad hace
    # comparables dos facturas antes de ordenarlas por similitud semántica.
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS metadata JSONB "
    "NOT NULL DEFAULT '{}'::jsonb",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_metadata "
    "ON document_chunks USING gin (metadata)",
    # Índice vectorial HNSW para el operador de distancia coseno (`<=>`), que es el que usa
    # `search_similar`.
    #
    # Sin él, cada búsqueda compara la consulta contra TODOS los chunks del cliente. Con los
    # ochenta y pico de hoy eso no se nota, y por eso el problema es fácil de no ver: aparece
    # cuando el corpus crece, y aparece en el peor sitio —una sugerencia por documento, en
    # medio de una jornada de causación en cadena—, cuando ya no hay ocasión de crearlo con
    # calma. Crearlo ahora, con la tabla pequeña, cuesta milisegundos.
    #
    # HNSW y no IVFFlat: IVFFlat necesita entrenarse con datos ya cargados y hay que reconstruirlo
    # cuando el corpus cambia de tamaño, mientras que HNSW se construye incrementalmente. Aquí
    # los chunks entran de uno en uno, cada vez que se contabiliza un documento.
    #
    # `vector_cosine_ops` DEBE coincidir con el operador de la consulta: un índice creado con
    # otra clase de operadores no se usa —la consulta sigue funcionando, en escaneo secuencial,
    # sin avisar de nada—.
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
    "ON document_chunks USING hnsw (embedding vector_cosine_ops)",
)


def run_tenant_migrations(engine, tenant_slug: str = "") -> None:
    """Aplica las migraciones sobre la base indicada. Nunca lanza.

    Un fallo aquí no puede tumbar el arranque del servicio ni el aprovisionamiento de un
    cliente, pero tampoco puede pasar desapercibido: se registra con el detalle de la
    sentencia que falló.
    """
    for statement in TENANT_MIGRATIONS:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Migración del rag-service falló (tenant=%s): %s | %s",
                tenant_slug or "default",
                statement.split("\n")[0][:120],
                exc,
            )
