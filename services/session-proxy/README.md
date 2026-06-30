# session-proxy

Puerto: **8004**

## Responsabilidad

Autenticacion en el portal DIAN, descarga de ZIPs de facturas electronicas y reenvio de requests HTTP al portal externo. Las descargas se ejecutan en background mediante una cola arq (Redis).

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| POST | `/api/v1/dian/sessions` | Autentica en el portal DIAN con token, captura cookies y crea sesion local |
| DELETE | `/api/v1/dian/sessions/{session_id}` | Elimina sesion local (idempotente) |
| POST | `/api/v1/dian/sessions/company` | Login via navegador automatizado (Playwright) para flujo de empresa; crea sesion local |
| POST | `/api/v1/dian/sessions/debug` | [DEBUG] Ejecuta login y retorna cookies capturadas sin crear sesion operativa |
| GET | `/api/v1/dian/sessions/{session_id}/debug` | [DEBUG] Retorna cookies y metadatos de una sesion almacenada |
| POST | `/api/v1/dian/downloads` | Consulta DIAN por rango de fechas y encola descarga de ZIPs en background; retorna `batch_id` |
| GET | `/api/v1/dian/documents/batches/{batch_id}` | Estado del batch de descarga con resumen por etapa (`downloaded`, `xml_processed`, `accounting`); `?detail=true` incluye progreso por job |
| GET | `/api/v1/dian/documents/jobs/{job_id}` | Estado de un job individual dentro del pipeline de descarga y procesamiento |
| POST | `/api/v1/proxy/request` | Reenvia una peticion HTTP arbitraria al portal externo usando cookies de sesion |

## Dependencias internas

- **Redis** — cola arq para jobs de descarga en background (`REDIS_URL`)
- **Portal DIAN externo** (`catalogo-vpfe.dian.gov.co`) — autenticacion y descarga de ZIPs; no tiene API publica, por lo que el login interactivo usa Playwright

## Variables de entorno

| Variable | Descripcion |
|----------|-------------|
| `EXTERNAL_BASE_URL` | URL base del portal externo (ej. `https://catalogo-vpfe.dian.gov.co`) |
| `EXTERNAL_LOGIN_PATH` | Path del endpoint de autenticacion (ej. `/User/AuthToken`) |
| `SESSION_TTL_SECONDS` | TTL de sesiones en memoria (por defecto `3600`) |
| `REDIS_URL` | URL de Redis para la cola arq (ej. `redis://redis:6379`) |

## Tests

```bash
docker run --rm -v "$(pwd)/services/session-proxy:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

## Decisiones de diseno

- Playwright para login via browser: el portal DIAN no expone API publica de autenticacion para flujos de empresa.
- Las sesiones se almacenan en memoria con TTL configurable; multiples requests pueden reutilizar la misma sesion sin reautenticar.
- Las descargas batch se encolan en Redis (arq) para no bloquear el request HTTP; el cliente monitorea el progreso con `GET /dian/documents/batches/{batch_id}`.
- El batch_id expira en Redis tras 7 dias; pasado ese plazo `GET /batches/{id}` retorna 404.
- `POST /proxy/request` permite operar contra el portal DIAN cuando no existe un endpoint especializado, usando las cookies de una sesion ya creada.
