"""Mide si el RAG recupera el precedente que debía recuperar.

POR QUÉ HACE FALTA
──────────────────
Hasta ahora no había forma de responder «¿está funcionando la recuperación?». Las pruebas
comprueban el CONTRATO —que el filtro se aplique antes del LIMIT, que solo salgan chunks
validados—, no la CALIDAD: pasarían igual con un embedding que devolviera ruido. Y sin una
cifra, cualquier cambio en el prompt, en el modelo de embeddings o en los rasgos indexados es
un cambio a ciegas: se nota cuando un contador se queja, no cuando se despliega.

QUÉ MIDE, SIN NECESIDAD DE ETIQUETAR NADA
─────────────────────────────────────────
Dos cosas, ambas derivables del propio corpus:

1. **Auto-recuperación (recall@k).** Cada chunk validado es a la vez consulta y respuesta
   esperada: se busca con su propio texto y se comprueba que él mismo aparece entre los `k`
   primeros. Es el suelo del sistema, no el techo: si un documento no se encuentra ni a sí
   mismo, la recuperación está rota —embedding mal calculado, índice con la clase de
   operadores equivocada, filtro que descarta de más—. Se espera 100 %; cualquier cosa por
   debajo es un defecto, no un matiz.

2. **Separación.** La distancia entre la similitud del propio chunk y la del mejor vecino
   distinto. Es lo que dice si el umbral está bien puesto: si el vecino más parecido saca 0.95
   sobre 1.0 del propio, no hay umbral que distinga un precedente de un documento cualquiera,
   y el problema está en lo que se indexa, no en el corte.

Y sobre esas dos, el reparto de similitudes: cuántos pares del corpus superan el umbral por
defecto. Un corpus donde TODO lo supera indica un umbral inútil; uno donde no lo supera nada,
un corpus sin casos comparables todavía.

LO QUE NO MIDE
──────────────
Si la retención sugerida fue la correcta. Eso exige facturas etiquetadas por un contador y es
la evaluación de RF-08, no la del RAG. Ésta responde una pregunta anterior y necesaria: si el
contexto que se le da al modelo es el que corresponde al caso.

USO
───
    python scripts/evaluate_retrieval.py                 # sobre los chunks validados
    python scripts/evaluate_retrieval.py --all           # incluye los no validados
    python scripts/evaluate_retrieval.py --top-k 3
"""

import argparse
import logging
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.application.dto.chunk import DEFAULT_MIN_SIMILARITY  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("eval")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    usuario = os.getenv("DATABASE_USER", "master")
    clave = os.getenv("DATABASE_PASSWORD", "master")
    host = os.getenv("DATABASE_HOST", "localhost")
    puerto = os.getenv("DATABASE_PORT", "5433")
    nombre = os.getenv("DATABASE_NAME", "abacus_t_ikbo")
    return f"postgresql://{usuario}:{clave}@{host}:{puerto}/{nombre}"


def _corpus(session: Session, solo_validados: bool) -> list[dict]:
    condicion = "embedding IS NOT NULL" + (" AND is_validated IS TRUE" if solo_validados else "")
    filas = session.execute(
        text(f"SELECT id, source_id, metadata FROM document_chunks WHERE {condicion} ORDER BY id")  # noqa: S608
    ).mappings()
    return [dict(f) for f in filas]


def _vecinos(session: Session, chunk_id: int, top_k: int, solo_validados: bool) -> list[dict]:
    """Los `top_k` más cercanos al chunk dado, usando SU PROPIO embedding como consulta.

    La consulta se hace con el embedding ya almacenado y no volviendo a llamar al proveedor:
    evalúa el índice y la métrica, que es lo que aquí se mide, y no cuesta ni una petición.
    """
    condicion = "c.embedding IS NOT NULL" + (" AND c.is_validated IS TRUE" if solo_validados else "")
    filas = session.execute(
        text(
            f"""
            SELECT c.id, c.source_id,
                   1 - (c.embedding <=> (SELECT embedding FROM document_chunks WHERE id = :id))
                       AS similarity
            FROM document_chunks c
            WHERE {condicion}
            ORDER BY c.embedding <=> (SELECT embedding FROM document_chunks WHERE id = :id)
            LIMIT :k
            """  # noqa: S608
        ),
        {"id": chunk_id, "k": top_k},
    ).mappings()
    return [dict(f) for f in filas]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5, help="vecinos a considerar (por defecto 5)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="evalúa todo el corpus, no solo el conocimiento validado",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=DEFAULT_MIN_SIMILARITY,
        help=f"umbral a contrastar (por defecto {DEFAULT_MIN_SIMILARITY})",
    )
    args = parser.parse_args()
    solo_validados = not args.all

    engine = create_engine(_database_url())
    with Session(engine) as session:
        corpus = _corpus(session, solo_validados)
        if not corpus:
            logger.warning(
                "No hay chunks %s con embedding: nada que evaluar.",
                "validados" if solo_validados else "",
            )
            return 0

        logger.info(
            "Corpus: %d chunk(s) %s · top_k=%d · umbral=%.2f",
            len(corpus),
            "validados" if solo_validados else "(todos)",
            args.top_k,
            args.min_similarity,
        )
        logger.info("")

        encontrados = 0
        separaciones: list[float] = []
        mejores_vecinos: list[float] = []
        fallos: list[int] = []

        for chunk in corpus:
            vecinos = _vecinos(session, chunk["id"], args.top_k, solo_validados)
            ids = [v["id"] for v in vecinos]
            if chunk["id"] in ids:
                encontrados += 1
            else:
                fallos.append(chunk["id"])

            propio = next((v["similarity"] for v in vecinos if v["id"] == chunk["id"]), None)
            ajenos = [v["similarity"] for v in vecinos if v["id"] != chunk["id"]]
            if ajenos:
                mejores_vecinos.append(max(ajenos))
                if propio is not None:
                    separaciones.append(propio - max(ajenos))

        recall = encontrados / len(corpus)
        logger.info("Auto-recuperación (recall@%d): %.0f %% (%d/%d)",
                    args.top_k, recall * 100, encontrados, len(corpus))
        if fallos:
            logger.warning("  ⚠ chunks que no se encuentran ni a sí mismos: %s", fallos)
            logger.warning("    Revise el índice HNSW (`vector_cosine_ops`) y los embeddings.")

        if mejores_vecinos:
            sobre_umbral = sum(1 for s in mejores_vecinos if s >= args.min_similarity)
            logger.info("")
            logger.info("Mejor vecino distinto — similitud:")
            logger.info("  mediana %.3f · mín %.3f · máx %.3f",
                        statistics.median(mejores_vecinos),
                        min(mejores_vecinos), max(mejores_vecinos))
            logger.info(
                "  superan el umbral %.2f: %d de %d (%.0f %%)",
                args.min_similarity, sobre_umbral, len(mejores_vecinos),
                100 * sobre_umbral / len(mejores_vecinos),
            )
            if separaciones:
                logger.info("  separación mediana respecto al propio: %.3f",
                            statistics.median(separaciones))

            if sobre_umbral == len(mejores_vecinos):
                logger.warning(
                    "  ⚠ TODO el corpus supera el umbral: no está discriminando nada. "
                    "Súbalo o revise qué se indexa."
                )
            elif sobre_umbral == 0:
                logger.warning(
                    "  ⚠ NADA supera el umbral: hoy el RAG no aporta precedentes. Con un corpus "
                    "pequeño es lo esperable; conviene revisarlo al crecer."
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
