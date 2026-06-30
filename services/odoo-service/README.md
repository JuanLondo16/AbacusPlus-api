# odoo-service

## Responsabilidad

Sincroniza facturas de compra desde Odoo y vincula los asientos contables de Odoo con documentos DIAN procesados por xml-processor. No genera ni modifica asientos en Odoo.

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| POST | `/api/v1/odoo/syncs` | Extrae facturas de compra (`move_type = in_invoice`) de Odoo por rango de fechas y las almacena localmente. Idempotente por `source_id`. |
| GET  | `/api/v1/odoo/entries` | Lista asientos almacenados localmente. Filtros opcionales: `date_from`, `date_to`, `move_type`, `state`. |
| POST | `/api/v1/odoo/entry-matches` | Vincula asientos `in_invoice` sin documento DIAN asociado, cruzando por fecha exacta, NIT del emisor y total (tolerancia ±1 COP). |
| GET  | `/api/v1/odoo/entries/document/{document_id}` | Retorna el ultimo asiento contable vinculado a un documento DIAN. |
| GET  | `/api/v1/odoo/entries/{entry_id}` | Detalle de un asiento con todas sus lineas contables. |
| GET  | `/health` | Health check. |

## Dependencias internas

- **Odoo** (`ODOO_URL`): XML-RPC para leer facturas de compra
- **xml-processor**: referencia cruzada de documentos por NIT/numero de factura durante el matching

## Variables de entorno

```
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USER=admin
ODOO_PASSWORD=admin
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_USER=master
DATABASE_PASSWORD=master
DATABASE_NAME=abacus
```

## Tests

```bash
docker run --rm -v "$(pwd)/services/odoo-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

## Decisiones de diseno

- La vinculacion entre asientos Odoo y documentos DIAN es best-effort (por fecha exacta + NIT normalizado + total con tolerancia ±1 COP).
- Solo lectura desde Odoo; no escribe de vuelta ni modifica asientos en el sistema externo.
- La sincronizacion (`POST /odoo/syncs`) es idempotente: re-ejecutar actualiza los campos existentes sin duplicar registros.
- En multi-tenant, el endpoint interno `POST /internal/provision-tenant` (no expuesto en Swagger) crea las tablas del servicio en la base del tenant indicado.
