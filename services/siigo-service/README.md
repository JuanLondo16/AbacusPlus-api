# siigo-service

## Responsabilidad

Autenticacion en la API de SIIGO, sincronizacion del plan de cuentas hacia integration-config-service, envio de asientos contables (comprobantes de causacion) a SIIGO Nube y gestion de plantillas de parametros para facturas de compra.

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| POST | `/api/v1/siigo/sessions` | Autentica contra SIIGO usando credenciales locales y persiste el `access_token`. Usar cuando cambien credenciales o para forzar renovacion. |
| POST | `/api/v1/siigo/chart-accounts/syncs` | Consulta el plan de cuentas de SIIGO y alimenta la tabla local `integration_chart_accounts`. |
| POST | `/api/v1/siigo/journal-entries` | Envia un asiento contable (comprobante de causacion) a SIIGO como `journal-voucher`. Valida que debitos == creditos (tolerancia ±0.05) y renueva token automaticamente si esta vencido. |
| POST | `/api/v1/siigo/purchase-invoice-parameters` | Guarda una plantilla local con los parametros que SIIGO requiere para crear facturas de compra. |
| GET  | `/api/v1/siigo/purchase-invoice-parameters` | Lista las plantillas locales de parametros para facturas de compra. Filtro: `account_key`. |
| GET  | `/health` | Health check. |

## Dependencias internas

- **SIIGO API** (`SIIGO_BASE_URL`): fuente del plan de cuentas y destino de los asientos contables
- **integration-config-service**: destino donde se importan las cuentas sincronizadas (via `chart-accounts/syncs`)

## Variables de entorno

```
SIIGO_BASE_URL=https://api.siigo.com
SIIGO_CHART_ACCOUNTS_PATH=/v1/accounts
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_USER=master
DATABASE_PASSWORD=master
DATABASE_NAME=abacus
```

## Tests

```bash
docker run --rm -v "$(pwd)/services/siigo-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

## Decisiones de diseno

- El token SIIGO se persiste en BD para evitar re-autenticar en cada request; se renueva automaticamente cuando esta vencido al enviar asientos.
- La sincronizacion de cuentas es on-demand (`POST /siigo/chart-accounts/syncs`), no automatica.
- El envio de asientos valida cuadre contable antes de llamar a SIIGO; si debitos != creditos (tolerancia ±0.05 COP), retorna `400` sin llamar al API externo.
- El campo `centro_costo` en las lineas del asiento debe ser el ID entero de SIIGO, no el codigo texto.
- En multi-tenant, el endpoint interno `POST /internal/provision-tenant` (no expuesto en Swagger) crea las tablas del servicio en la base del tenant indicado.
