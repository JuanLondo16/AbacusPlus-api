# integration-config-service

## Responsabilidad

Catalogo centralizado agnostico al proveedor: plan de cuentas PUC, centros de costo, impuestos, tipos de pago, productos/servicios, credenciales de integracion y plantillas de parametros para facturas de compra. Es la fuente de verdad que consumen xml-processor y llm-service.

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| PUT    | `/api/v1/integrations/credentials` | Crea o actualiza credenciales de integracion (SIIGO, Odoo, u otros). Agnostico al proveedor via `provider` + `account_key`. |
| GET    | `/api/v1/integrations/credentials` | Lista credenciales configuradas. Los secretos (`access_key`, `access_token`) no se exponen. Filtro: `provider`. |
| GET    | `/api/v1/integrations/chart-accounts` | Lista el plan de cuentas almacenado localmente. Filtro: `active`. |
| POST   | `/api/v1/integrations/chart-accounts/imports` | Importa plan de cuentas desde `.xlsx`. Idempotente por `account_key` + `code`. Modo `upsert` (default) o `replace`. |
| GET    | `/api/v1/integrations/cost-centers` | Lista centros de costo registrados localmente. Filtro: `active`. |
| POST   | `/api/v1/integrations/cost-centers/imports` | Importa centros de costo desde `.xlsx`. Idempotente por `code`. |
| GET    | `/api/v1/integrations/taxes` | Lista impuestos registrados localmente. Filtro: `active`. |
| POST   | `/api/v1/integrations/taxes/imports` | Importa impuestos desde `.xlsx`. Idempotente por `name`. |
| POST   | `/api/v1/integrations/taxes/siigo-syncs` | Sincroniza impuestos desde `GET /v1/taxes` de SIIGO. Autentica automaticamente si el token expiró. |
| GET    | `/api/v1/integrations/payment-types` | Lista tipos de pago registrados localmente. Filtro: `active`. |
| POST   | `/api/v1/integrations/payment-types/imports` | Importa tipos de pago desde `.xlsx`. Idempotente por `name`. |
| POST   | `/api/v1/integrations/payment-types/siigo-syncs` | Sincroniza tipos de pago desde `GET /v1/payment-types` de SIIGO. |
| GET    | `/api/v1/integrations/products` | Lista productos y servicios registrados localmente. Filtros: `active`, `type` (`product`\|`service`). |
| POST   | `/api/v1/integrations/products/imports` | Importa productos y servicios desde `.xlsx`. Idempotente por `code`. |
| POST   | `/api/v1/integrations/purchase-invoice-parameters` | Guarda plantilla de parametros para facturas de compra (agnostica al proveedor via `provider`). |
| GET    | `/api/v1/integrations/purchase-invoice-parameters` | Lista plantillas de parametros. Filtros: `provider`, `account_key`. |
| GET    | `/health` | Health check. |

## Dependencias internas

Ninguna — es un servicio de configuracion que otros servicios consumen.

Los endpoints de `siigo-syncs` llaman a la API de SIIGO directamente usando las credenciales almacenadas localmente.

## Variables de entorno

```
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_USER=master
DATABASE_PASSWORD=master
DATABASE_NAME=abacus
```

## Tests

```bash
docker run --rm -v "$(pwd)/services/integration-config-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

## Decisiones de diseno

- Diseno agnostico al proveedor: el plan de cuentas PUC, impuestos y tipos de pago se pueden importar desde SIIGO, Odoo u otro sistema via `.xlsx` o mediante syncs directos.
- En multi-tenant, este servicio debe provisionarse antes que xml-processor (hay dependencias de FK cruzadas). El endpoint interno `POST /internal/provision-tenant` (no expuesto en Swagger) crea las tablas del servicio en la base del tenant indicado.
- Las credenciales se guardan sin secretos en el endpoint `GET /credentials` (los valores sensibles como `access_key` y `access_token` no se exponen).
- Todas las importaciones desde Excel son idempotentes: re-ejecutar con el mismo archivo no genera duplicados.
