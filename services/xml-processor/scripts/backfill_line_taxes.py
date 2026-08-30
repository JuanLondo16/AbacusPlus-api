"""Rellena `document_details.taxes` en los documentos procesados antes de que existiera.

EL PROBLEMA QUE RESUELVE
────────────────────────
La columna `taxes` guarda TODOS los impuestos de la línea tal como los declara la DIAN, con su
esquema («01» IVA, «04» INC, «22» INC bolsas, «02» IC). Es lo que permite separar el IVA del
impuesto al consumo: cada uno con su tarifa y su importe.

Los documentos anteriores a esa columna solo tienen `tax_type` y `tax_value`, que guardan el
impuesto PRINCIPAL de la línea —el de mayor importe— sin decir de qué clase es. La interfaz,
al no poder saberlo, cae en el único supuesto que puede hacer: lo muestra como IVA. En una
factura como la F78P21635, cuyas dos líneas llevan Impoconsumo del 8 % y NINGÚN IVA, eso pinta
un «IVA 8 %» que no existe y deja la columna de INC vacía.

No es solo un rótulo equivocado: el impuesto al consumo tiene cuenta contable propia, y un
contador que revisa el documento en pantalla ve un impuesto que no es el que le cobraron.

CÓMO LO RESUELVE
────────────────
El XML original está guardado en `documents.xml_data`. Se vuelve a leer con el MISMO parser y
las MISMAS funciones de dominio que usa el procesamiento normal (`parse_xml`,
`extraer_impuestos_de_linea`, `resolver_impuesto`), así que el resultado es idéntico al que
tendría el documento si se procesara hoy. No se inventa nada ni se recalcula ningún total.

QUÉ NO TOCA
───────────
- Solo escribe `document_details.taxes`, y solo donde está vacío.
- No modifica `tax_type`, `tax_value`, `tax_id`, subtotales ni totales: lo ya contabilizado
  no cambia de importe por ejecutar esto.
- Si el XML no se puede leer, o el número de líneas del XML no coincide con el de la base,
  el documento se salta y se informa. Emparejar líneas a ciegas sería peor que no hacer nada.

USO
───
    python scripts/backfill_line_taxes.py            # simulacro: no escribe nada
    python scripts/backfill_line_taxes.py --apply    # aplica los cambios

    DATABASE_URL=postgresql://... python scripts/backfill_line_taxes.py --apply
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domain.services.line_taxes import extraer_impuestos_de_linea  # noqa: E402
from app.domain.services.tax_resolution import resolver_impuesto  # noqa: E402
from app.utils.xml_parser import parse_xml  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill")


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


def _catalogo(session: Session) -> list[dict]:
    """Catálogo de impuestos, para enlazar cada impuesto de línea con su id de SIIGO."""
    filas = session.execute(
        text("SELECT id, name, type, percentage FROM integration_taxes WHERE active = true")
    ).mappings()
    return [dict(f) for f in filas]


def _documentos_pendientes(session: Session) -> list[dict]:
    filas = session.execute(
        text(
            """
            SELECT DISTINCT d.id, d.document_number
            FROM documents d
            JOIN document_details dd ON dd.document_id = d.id
            WHERE dd.taxes IS NULL AND d.xml_data IS NOT NULL
            ORDER BY d.id
            """
        )
    ).mappings()
    return [dict(f) for f in filas]


def _lineas(session: Session, document_id: int) -> list[dict]:
    filas = session.execute(
        text(
            """
            SELECT id, description, subtotal, tax_type, tax_value, taxes
            FROM document_details
            WHERE document_id = :doc
            ORDER BY id
            """
        ),
        {"doc": document_id},
    ).mappings()
    return [dict(f) for f in filas]


def _xml(session: Session, document_id: int) -> str:
    dato = session.execute(
        text("SELECT xml_data FROM documents WHERE id = :doc"), {"doc": document_id}
    ).scalar()
    if dato is None:
        raise ValueError("sin xml_data")
    if isinstance(dato, memoryview):
        dato = dato.tobytes()
    if isinstance(dato, bytes):
        return dato.decode("utf-8", errors="replace")
    return str(dato)


def procesar(session: Session, catalogo: list[dict], aplicar: bool) -> tuple[int, int, int]:
    """Devuelve (documentos actualizados, líneas actualizadas, documentos saltados)."""
    documentos = _documentos_pendientes(session)
    logger.info("Documentos con líneas sin desglose de impuestos: %d", len(documentos))

    docs_ok = lineas_ok = saltados = 0

    for doc in documentos:
        try:
            datos = parse_xml(_xml(session, doc["id"]))
        except Exception as exc:  # el XML es de un tercero: puede estar corrupto
            logger.warning("· %s — no se pudo leer el XML (%s): se salta", doc["document_number"], exc)
            saltados += 1
            continue

        items = datos.get("items") or []
        lineas = _lineas(session, doc["id"])

        # Emparejar por posición solo es válido si hay el mismo número de líneas: las líneas se
        # insertaron en el orden del XML. Si no cuadra, no se adivina.
        if len(items) != len(lineas):
            logger.warning(
                "· %s — el XML trae %d líneas y la base %d: se salta",
                doc["document_number"],
                len(items),
                len(lineas),
            )
            saltados += 1
            continue

        cambios: list[tuple[int, list[dict]]] = []
        for item, linea in zip(items, lineas):
            if linea["taxes"] is not None:
                continue
            impuestos = extraer_impuestos_de_linea(item.get("impuestos"))
            if not impuestos:
                continue
            for impuesto in impuestos:
                impuesto["tax_id"] = resolver_impuesto(
                    str(impuesto.get("porcentaje") or 0),
                    catalogo,
                    nombre=str(impuesto.get("nombre") or ""),
                )
            cambios.append((linea["id"], impuestos))

        if not cambios:
            continue

        resumen = ", ".join(
            f"{linea_id}:[" + " ".join(f"{i['esquema']}@{i['porcentaje']}%" for i in imps) + "]"
            for linea_id, imps in cambios
        )
        logger.info("· %s — %d línea(s): %s", doc["document_number"], len(cambios), resumen)

        if aplicar:
            for linea_id, impuestos in cambios:
                session.execute(
                    text("UPDATE document_details SET taxes = CAST(:t AS json) WHERE id = :id"),
                    {"t": __import__("json").dumps(impuestos), "id": linea_id},
                )

        docs_ok += 1
        lineas_ok += len(cambios)

    if aplicar:
        session.commit()

    return docs_ok, lineas_ok, saltados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="escribe los cambios; sin este parámetro solo se listan",
    )
    args = parser.parse_args()

    engine = create_engine(_database_url())
    with Session(engine) as session:
        catalogo = _catalogo(session)
        if not catalogo:
            logger.warning(
                "El catálogo de impuestos está vacío: los impuestos se rellenarán sin `tax_id`."
            )
        docs, lineas, saltados = procesar(session, catalogo, args.apply)

    modo = "APLICADO" if args.apply else "SIMULACRO (nada se escribió)"
    logger.info("")
    logger.info("%s — %d documento(s), %d línea(s), %d saltado(s)", modo, docs, lineas, saltados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
