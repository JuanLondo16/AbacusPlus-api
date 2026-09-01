import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.entities.chunk import ChunkEntity
from app.domain.ports.repositories import ChunkRepositoryPort
from app.infrastructure.persistence.models.chunk import DocumentChunk

logger = logging.getLogger(__name__)


class ChunkRepository(ChunkRepositoryPort):
    def __init__(self, db: Session):
        self.db = db

    def delete_by_source(self, source_type: str, source_id: int) -> int:
        """Elimina los chunks previos de una fuente (upsert por documento).

        El reindexado al aprobar un documento vuelve a generar su chunk con las decisiones
        confirmadas (cuentas y retenciones). Sin borrar el anterior se acumularían versiones
        obsoletas del mismo documento y la búsqueda devolvería datos contradictorios.
        """
        deleted = (
            self.db.query(DocumentChunk)
            .filter(
                DocumentChunk.source_type == source_type,
                DocumentChunk.source_id == source_id,
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def create(self, chunk: ChunkEntity) -> ChunkEntity:
        embedding_str = f"[{','.join(map(str, chunk.embedding))}]" if chunk.embedding else None
        db_chunk = DocumentChunk(
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            content=chunk.content,
            is_validated=chunk.is_validated,
            validated_at=chunk.validated_at,
            siigo_id=chunk.siigo_id,
            doc_metadata=chunk.metadata or {},
        )
        self.db.add(db_chunk)
        self.db.flush()  # obtener el id antes del commit

        if embedding_str:
            self.db.execute(
                text("UPDATE document_chunks SET embedding = CAST(:emb AS vector) WHERE id = :id"),
                {"emb": embedding_str, "id": db_chunk.id},
            )

        self.db.commit()
        self.db.refresh(db_chunk)

        chunk.id = db_chunk.id
        chunk.created_at = db_chunk.created_at
        return chunk

    #: Claves de metadata admitidas como filtro. Es una lista blanca a propósito: los
    #: nombres de clave se interpolan en el SQL (JSONB no admite parámetro en la ruta), así
    #: que aceptar claves arbitrarias del cliente abriría una inyección. Todo lo que no esté
    #: aquí se ignora en silencio, que es el comportamiento seguro: se recupera de más, nunca
    #: se ejecuta algo inesperado.
    ALLOWED_FILTER_KEYS = frozenset(
        {
            "issuer_nit",
            "municipality_code",
            "retention_types",
            "account_codes",
            "concept",
            "regimen",
            "document_type",
        }
    )

    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        only_validated: bool = False,
        filters: Optional[dict] = None,
        min_similarity: float = 0.0,
    ) -> list[dict]:
        """Búsqueda híbrida: filtros estructurados + similitud coseno (pgvector `<=>`).

        `only_validated` es el filtro de RF-08: restringe el resultado al conocimiento de
        causaciones contabilizadas en SIIGO.

        `filters` es la mitad estructurada de la búsqueda. Existe porque el embedding no
        sabe qué es un NIT: dos facturas del mismo proveedor y el mismo concepto son el
        precedente que se busca aunque no compartan una palabra, y dos textos casi idénticos
        de proveedores con régimen distinto llevan a retenciones distintas. Filtrar por los
        rasgos que de verdad hacen comparables dos casos, y ordenar por similitud solo
        dentro de ese conjunto, es lo que convierte «tres vecinos textuales» en «tres
        precedentes».

        `min_similarity` es el umbral por debajo del cual un chunk deja de considerarse
        parecido. Sin él, esta consulta no puede responder «no hay nada»: ordena por distancia
        y corta en `top_k`, así que mientras existan chunks devuelve siempre los menos malos.
        Quien la llama no puede distinguir un precedente real de un vecino cualquiera, y en
        RF-08 ese vecino entra al prompt rotulado como causación contabilizada.

        Todo va en el SQL antes del `LIMIT`, nunca sobre el resultado: filtrar después
        dejaría que un vecino descartable ocupara uno de los `top_k` puestos y redujera en
        silencio el contexto recuperado. El umbral, por el mismo motivo, se expresa como
        distancia máxima en el `WHERE` —`embedding <=> :emb <= 1 - umbral`, que es la forma
        que el índice puede aprovechar— y no como un filtro sobre la similitud calculada.
        """
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        params: dict = {"emb": embedding_str, "top_k": top_k}
        conditions: list[str] = ["embedding IS NOT NULL"]
        if only_validated:
            conditions.append("is_validated IS TRUE")
        if min_similarity > 0:
            # `similarity = 1 - distancia`, así que el umbral de similitud es un techo de
            # distancia. Se escribe así, y no como `1 - (...) >= umbral`, porque la
            # comparación directa sobre el operador es la que el índice HNSW puede usar.
            params["max_dist"] = 1.0 - float(min_similarity)
            conditions.append("(embedding <=> CAST(:emb AS vector)) <= :max_dist")

        for i, (key, value) in enumerate(sorted((filters or {}).items())):
            if key not in self.ALLOWED_FILTER_KEYS or value in (None, "", [], {}):
                continue
            param = f"f{i}"
            if isinstance(value, (list, tuple, set)):
                # «Cualquiera de». El valor almacenado puede ser un escalar (`municipality_code`)
                # o una lista (`retention_types`), así que se normaliza a array dentro del
                # propio SQL y se compara elemento a elemento.
                #
                # No se usa el operador `?|` de JSONB —que sería lo natural— porque el signo
                # de interrogación colisiona con el marcador de parámetros de algunos drivers
                # y convierte la consulta en un error difícil de rastrear. Esta forma es
                # equivalente y no depende del paramstyle.
                params[param] = [str(v) for v in value]
                conditions.append(
                    f"""EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(
                            CASE WHEN jsonb_typeof(metadata->'{key}') = 'array'
                                 THEN metadata->'{key}'
                                 ELSE jsonb_build_array(metadata->'{key}')
                            END
                        ) AS v WHERE v = ANY(CAST(:{param} AS text[]))
                    )""",  # noqa: S608 — `key` sale de ALLOWED_FILTER_KEYS; el valor va ligado
                )
            else:
                params[param] = str(value)
                conditions.append(f"metadata->>'{key}' = :{param}")

        where = " AND ".join(conditions)
        rows = self.db.execute(
            # nosemgrep: avoid-sqlalchemy-text
            text(f"""
                SELECT id, source_type, source_id, content, is_validated, siigo_id,
                       metadata,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM document_chunks
                WHERE {where}
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :top_k
            """),  # noqa: S608 — solo se interpolan claves de la lista blanca de arriba
            params,
        ).fetchall()

        return [
            {
                "id": r[0],
                "source_type": r[1],
                "source_id": r[2],
                "content": r[3],
                "is_validated": bool(r[4]),
                "siigo_id": r[5],
                "metadata": r[6] or {},
                "similarity": round(float(r[7]), 4),
            }
            for r in rows
        ]
