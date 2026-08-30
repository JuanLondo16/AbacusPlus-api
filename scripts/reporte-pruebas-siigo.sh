#!/usr/bin/env bash
# Reporte de una sesión de pruebas de contabilización en SIIGO (RF-05).
#
# Produce tres listas y las deja listas para pegar en un correo:
#   1. Contabilizados con éxito  → los que el contador debe eliminar en SIIGO
#   2. Desenlace incierto        → verificar MANUALMENTE en SIIGO antes de dar por cerrada la limpieza
#   3. Con error                 → no llegaron a crearse; no hay nada que eliminar
#
# Uso:
#   ./reporte-pruebas-siigo.sh                      # todo lo contabilizado
#   ./reporte-pruebas-siigo.sh '2026-08-22 14:00'   # solo desde esa fecha/hora
set -euo pipefail

TENANT="${TENANT:-ikbo}"
DB="abacus_t_${TENANT}"
DESDE="${1:-1900-01-01}"

psql() { docker exec abacus_db psql -U master -d "$DB" "$@"; }

echo "REPORTE DE PRUEBAS — CONTABILIZACIÓN EN SIIGO"
echo "Empresa: ${TENANT}   ·   Generado: $(date '+%Y-%m-%d %H:%M')"
echo "Ventana considerada: desde ${DESDE}"
echo
echo "=============================================================================="
echo "1. CONTABILIZADOS CON ÉXITO — a eliminar en SIIGO"
echo "=============================================================================="
psql -P pager=off -c "
SELECT to_char(accounted_at, 'YYYY-MM-DD HH24:MI') AS \"Fecha\",
       siigo_name      AS \"Consecutivo SIIGO\",
       document_number AS \"Factura DIAN\",
       issuer_name     AS \"Proveedor\",
       issuer_nit      AS \"NIT\",
       to_char(total, 'FM999,999,999,990') AS \"Total\",
       siigo_id        AS \"ID interno SIIGO\"
  FROM documents
 WHERE siigo_id IS NOT NULL AND accounted_at >= '${DESDE}'
 ORDER BY accounted_at;"

echo
echo "=============================================================================="
echo "2. DESENLACE INCIERTO — verificar manualmente en SIIGO"
echo "=============================================================================="
echo "Estos NO tienen identificador de SIIGO, pero la petición pudo haber llegado."
echo "Búsquelos en SIIGO por el número de factura del proveedor antes de cerrar la limpieza."
psql -P pager=off -c "
SELECT id AS \"Doc Abacus\", document_number AS \"Factura DIAN\",
       issuer_name AS \"Proveedor\", issuer_nit AS \"NIT\",
       to_char(total, 'FM999,999,999,990') AS \"Total\",
       left(coalesce(accounting_error, '—'), 70) AS \"Motivo\"
  FROM documents
 WHERE status = 350 OR id IN (
   SELECT document_id FROM accounting_jobs WHERE recommended_action = 'VERIFICAR_EN_SIIGO'
 )
 ORDER BY id;"

echo
echo "=============================================================================="
echo "3. CON ERROR — no se creó nada en SIIGO"
echo "=============================================================================="
psql -P pager=off -c "
SELECT j.document_id AS \"Doc Abacus\", d.document_number AS \"Factura DIAN\",
       d.issuer_name AS \"Proveedor\", j.error_class AS \"Clase\",
       left(coalesce(j.last_error, '—'), 70) AS \"Error\"
  FROM accounting_jobs j JOIN documents d ON d.id = j.document_id
 WHERE j.state = 'FAILED' AND coalesce(j.recommended_action,'') <> 'VERIFICAR_EN_SIIGO'
 ORDER BY j.id;"

echo
echo "=============================================================================="
echo "COMPROBACIONES DE INTEGRIDAD (ambas deben devolver 0 filas)"
echo "=============================================================================="
echo "-- ¿Dos trabajos para un mismo documento?"
psql -P pager=off -c "SELECT document_id, COUNT(*) FROM accounting_jobs GROUP BY document_id HAVING COUNT(*) > 1;"
echo "-- ¿Dos documentos apuntando a la misma factura de SIIGO?"
psql -P pager=off -c "SELECT siigo_id, COUNT(*) FROM documents WHERE siigo_id IS NOT NULL GROUP BY siigo_id HAVING COUNT(*) > 1;"
