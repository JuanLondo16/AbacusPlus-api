# CLAUDE.md

Guía de contexto para Claude Code en este repositorio.

## Comandos rápidos

```bash
# Levantar todos los servicios
docker-compose up --build

# Levantar un solo servicio
docker-compose up --build xml-processor

# Ejecutar tests de un servicio
docker run --rm -v "$(pwd)/services/xml-processor:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"

# Instalar dependencias localmente (desarrollo)
pip install -r services/<servicio>/requirements.txt
```

## Arquitectura — Microservicios

El proyecto sigue una arquitectura de **microservicios**, cada uno con su propia
estructura hexagonal (Ports & Adapters). Los servicios se comunican vía **HTTP síncrono** (httpx).

```
Cliente
  │
  └─ :8000  ──►  gateway (Nginx)
                   │
                   ├─ POST /api/v1/documents  ──►  xml-processor :8001
                   │  GET  /api/v1/documents        │  procesa ZIP/XML → PostgreSQL
                   │  GET  /api/v1/receivers         └─ POST /api/v1/chunks  ──►  rag-service :8002
                   │  GET  /api/v1/issuers                                          (indexa embedding)
                   │  GET  /api/v1/catalog
                   │  POST /api/v1/batch-jobs
                   │  GET  /api/v1/batch-logs
                   │
                   ├─ POST /api/v1/query      ──►  llm-service :8003
                   │  POST /api/v1/analyses          │  POST /api/v1/chunks/search ──► rag-service :8002
                   │  POST /api/v1/accounting        └─ OpenAI API (prompt RAG-aumentado)
                   │
                   ├─ POST /api/v1/chunks     ──►  rag-service :8002  (debug/admin)
                   │
                   ├─ GET|POST /api/v1/odoo   ──►  odoo-service :8005
                   │                                (sync facturas compra, asientos)
                   │
                   ├─ GET|POST /api/v1/siigo  ──►  siigo-service :8006
                   │                                (credenciales, plan de cuentas)
                   │
                   ├─ GET|POST /api/v1/integrations ──►  integration-config-service :8007
                   │                                      (credenciales, centros costo, import)
                   │
                   ├─ POST /api/v1/dian       ──►  session-proxy :8004
                   │  POST /api/v1/proxy            (auth DIAN, descarga ZIPs, cola arq)
                   │
                   └─ GET  /health/*
```

## Estructura de carpetas

```
api/
├── services/
│   ├── gateway/                # Puerto 8000 (entrada única)
│   │   └── nginx.conf
│   │
│   ├── xml-processor/          # Puerto 8001
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   xml.py · documents.py · receivers.py
│   │   │   ├── application/use_cases/  process_xml.py · query_documents.py · query_receivers.py
│   │   │   ├── application/dto/        document.py · receiver.py
│   │   │   ├── domain/                 entities/ · exceptions/ · ports/ · value_objects/
│   │   │   ├── infrastructure/
│   │   │   │   ├── clients/            rag_client.py  ← HTTP client a rag-service
│   │   │   │   ├── config/             database.py · logging.py
│   │   │   │   └── persistence/        models/ · repositories/
│   │   │   └── utils/                  xml_parser.py · zip_handler.py · dian_dv.py · smart_match.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── rag-service/            # Puerto 8002
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   chunks.py  (POST /chunks, POST /chunks/search)
│   │   │   ├── application/use_cases/  index_chunk.py · search_chunks.py
│   │   │   ├── application/dto/        chunk.py
│   │   │   ├── domain/
│   │   │   │   ├── entities/           chunk.py  (ChunkEntity)
│   │   │   │   └── ports/              repositories.py · services.py (EmbeddingServicePort)
│   │   │   └── infrastructure/
│   │   │       ├── ai/                 ollama_service.py  ← OllamaEmbeddingService
│   │   │       ├── config/             database.py · logging.py
│   │   │       └── persistence/
│   │   │           ├── models/         chunk.py  (DocumentChunk + Vector(768))
│   │   │           └── repositories/   chunk_repository.py  (pgvector cosine search)
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── llm-service/            # Puerto 8003
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   analyze.py · query.py · accounting.py
│   │   │   ├── application/use_cases/  analyze_with_ai.py · query_with_rag.py · generate_accounting_entry.py
│   │   │   ├── application/dto/        ai.py · query.py · accounting.py
│   │   │   ├── domain/ports/           services.py  (AIServicePort · RagClientPort)
│   │   │   └── infrastructure/
│   │   │       ├── ai/                 openai_service.py
│   │   │       ├── clients/            rag_client.py · xml_processor_client.py
│   │   │       └── config/             logging.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── session-proxy/          # Puerto 8004
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   dian.py · proxy.py
│   │   │   ├── application/use_cases/  auth.py · download.py
│   │   │   ├── domain/                 entities/ · ports/
│   │   │   └── infrastructure/
│   │   │       ├── browser/            playwright_client.py
│   │   │       ├── config/             settings.py
│   │   │       └── workers/            download_worker.py  ← arq worker
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── odoo-service/           # Puerto 8005
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   odoo.py
│   │   │   ├── application/use_cases/  sync_invoices.py · match_entries.py
│   │   │   ├── domain/                 entities/ · ports/
│   │   │   └── infrastructure/
│   │   │       ├── clients/            odoo_client.py
│   │   │       ├── config/             database.py
│   │   │       └── persistence/        models/ · repositories/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── siigo-service/          # Puerto 8006
│   │   ├── app/
│   │   │   ├── adapters/api/routers/   chart_accounts.py · credentials.py · purchase_invoice_parameters.py
│   │   │   ├── application/use_cases/  sync_chart_accounts.py · authenticate.py
│   │   │   ├── domain/                 entities/ · ports/
│   │   │   └── infrastructure/
│   │   │       ├── clients/            siigo_client.py
│   │   │       ├── config/             database.py
│   │   │       └── persistence/        models/ · repositories/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── integration-config-service/  # Puerto 8007
│       ├── app/
│       │   ├── adapters/api/routers/   credentials.py · cost_centers.py · chart_accounts.py · purchase_invoice_parameters.py
│       │   ├── application/use_cases/  manage_credentials.py · import_cost_centers.py · import_chart_accounts.py
│       │   ├── domain/                 entities/ · ports/
│       │   └── infrastructure/
│       │       ├── config/             database.py
│       │       └── persistence/        models/ · repositories/
│       ├── tests/
│       ├── Dockerfile
│       └── requirements.txt
│
├── scripts/
│   └── init-db.sql             # CREATE EXTENSION IF NOT EXISTS vector
├── docker-compose.yml
├── .env
└── CLAUDE.md
```

## Flujo de datos

### Procesamiento de una factura
1. Cliente sube ZIP/XML → `gateway :8000` → `xml-processor`
2. `xml-processor` parsea, valida, guarda en PostgreSQL
3. `xml-processor` llama a `rag-service` (`POST /api/v1/chunks`) — **best-effort**
4. `rag-service` genera embedding con Ollama y guarda en `document_chunks` (pgvector)

### Consulta RAG
1. Cliente envía pregunta → `gateway :8000` → `llm-service`
2. `llm-service` llama a `rag-service` (`POST /api/v1/chunks/search`)
3. `rag-service` genera embedding de la query y retorna top-k chunks por similitud coseno
4. `llm-service` construye prompt aumentado y llama a OpenAI
5. Retorna respuesta + chunks utilizados + usage

## Endpoints por servicio

### gateway (:8000) — entrada única para clientes
| Método | Path | Destino |
|--------|------|---------|
| POST | `/api/v1/documents` | xml-processor |
| GET  | `/api/v1/documents/` | xml-processor |
| GET  | `/api/v1/documents/{id}` | xml-processor |
| GET  | `/api/v1/documents/{id}/full` | xml-processor |
| PATCH| `/api/v1/documents/{id}` | xml-processor |
| PATCH| `/api/v1/documents/{id}/approve` | xml-processor |
| GET  | `/api/v1/receivers` | xml-processor |
| GET  | `/api/v1/issuers/{nit}` | xml-processor |
| GET  | `/api/v1/catalog/*` | xml-processor |
| POST | `/api/v1/batch-jobs/*` | xml-processor |
| GET  | `/api/v1/batch-logs` | xml-processor |
| POST | `/api/v1/query` | llm-service |
| POST | `/api/v1/analyses` | llm-service |
| POST | `/api/v1/accounting/*` | llm-service |
| GET  | `/api/v1/accounting/*` | llm-service |
| PATCH| `/api/v1/accounting/*` | llm-service |
| POST | `/api/v1/chunks` | rag-service |
| POST | `/api/v1/chunks/search` | rag-service |
| GET  | `/api/v1/odoo/*` | odoo-service |
| POST | `/api/v1/odoo/*` | odoo-service |
| GET  | `/api/v1/siigo/*` | siigo-service |
| POST | `/api/v1/siigo/*` | siigo-service |
| GET  | `/api/v1/integrations/*` | integration-config-service |
| POST | `/api/v1/integrations/*` | integration-config-service |
| PUT  | `/api/v1/integrations/*` | integration-config-service |
| POST | `/api/v1/dian/*` | session-proxy |
| GET  | `/api/v1/dian/*` | session-proxy |
| DELETE | `/api/v1/dian/*` | session-proxy |
| POST | `/api/v1/proxy/*` | session-proxy |
| GET  | `/health` | gateway |
| GET  | `/health/xml-processor` | xml-processor |
| GET  | `/health/rag-service` | rag-service |
| GET  | `/health/llm-service` | llm-service |
| GET  | `/health/session-proxy` | session-proxy |
| GET  | `/health/odoo-service` | odoo-service |
| GET  | `/health/siigo-service` | siigo-service |
| GET  | `/health/integration-config-service` | integration-config-service |

### xml-processor (:8001) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/documents` | Procesa ZIP o XML DIAN, crea documento |
| GET  | `/api/v1/documents` | Lista documentos (`?from_date=&to_date=`) |
| GET  | `/api/v1/documents/{id}` | Detalle de un documento |
| GET  | `/api/v1/documents/{id}/full` | Documento + último asiento contable |
| PATCH| `/api/v1/documents/{id}/approve` | Aprueba documento (Causado → Aprobado) |
| PATCH| `/api/v1/documents/{id}` | Actualiza estado (`{"status": 200}` revierte a Causado) |
| GET  | `/api/v1/receivers` | Lista receptores |
| GET  | `/api/v1/issuers/{nit}` | Datos del emisor por NIT |
| GET  | `/api/v1/catalog/cost-centers` | Centros de costo activos |
| GET  | `/api/v1/catalog/puc-accounts` | Cuentas PUC activas |
| GET  | `/api/v1/catalog/retention-fuente-rates` | Tasas retención en la fuente |
| GET  | `/api/v1/catalog/retention-ica-rates` | Tasas retención ICA |
| POST | `/api/v1/batch-jobs/downloads` | Encolar ZIPs del directorio downloads |
| POST | `/api/v1/batch-jobs/file` | Encolar un ZIP específico |
| GET  | `/api/v1/batch-logs` | Historial de procesamiento batch |
| GET  | `/health` | Health check |

### rag-service (:8002) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/chunks` | Indexa un fragmento de texto con embedding |
| POST | `/api/v1/chunks/search` | Búsqueda semántica top-k |
| GET  | `/health` | Health check |

### llm-service (:8003) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/query` | Consulta RAG-aumentada con OpenAI |
| POST | `/api/v1/analyses` | Prompt directo a OpenAI sin RAG |
| POST | `/api/v1/accounting/entries` | Genera asiento contable para un documento |
| GET  | `/api/v1/accounting/entries/{document_id}` | Documento + último asiento contable |
| POST | `/api/v1/accounting/recalculations` | Recalcula asientos por rango de fechas |
| POST | `/api/v1/accounting/entries/{document_id}/recalculations` | Recalcula asiento de un documento |
| GET  | `/api/v1/accounting/system-prompts` | Lista prompts del sistema |
| POST | `/api/v1/accounting/system-prompts` | Crea nuevo prompt del sistema |
| PATCH| `/api/v1/accounting/system-prompts/{id}` | Actualiza prompt (`{"is_active": true}` activa) |
| GET  | `/health` | Health check |

### session-proxy (:8004) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/dian/sessions` | Autentica con token en portal DIAN, crea sesión local |
| DELETE | `/api/v1/dian/sessions/{session_id}` | Elimina sesión local |
| POST | `/api/v1/dian/sessions/company` | Login vía browser (Playwright), crea sesión |
| GET  | `/api/v1/dian/sessions/{session_id}/debug` | [DEBUG] Cookies y metadata de sesión |
| POST | `/api/v1/dian/sessions/debug` | [DEBUG] Intento de login sin crear sesión |
| POST | `/api/v1/dian/downloads` | Consulta DIAN y encola descargas de ZIPs |
| GET  | `/api/v1/dian/documents/batches/{batch_id}` | Estado del lote de descarga |
| GET  | `/api/v1/dian/documents/jobs/{job_id}` | Estado de un job individual |
| POST | `/api/v1/proxy/request` | Reenvía request HTTP al portal externo |
| GET  | `/health` | Health check |

### odoo-service (:8005) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/odoo/syncs` | Sincroniza facturas de compra desde Odoo |
| GET  | `/api/v1/odoo/entries` | Lista asientos locales (filtros: fecha, tipo, estado) |
| POST | `/api/v1/odoo/entry-matches` | Vincula asientos Odoo con documentos DIAN |
| GET  | `/api/v1/odoo/entries/document/{document_id}` | Último asiento vinculado a documento |
| GET  | `/api/v1/odoo/entries/{entry_id}` | Detalle de asiento con líneas |
| GET  | `/health` | Health check |

### siigo-service (:8006) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/siigo/sessions` | Autentica en SIIGO, persiste token |
| POST | `/api/v1/siigo/chart-accounts/syncs` | Sincroniza plan de cuentas desde SIIGO |
| GET  | `/api/v1/siigo/chart-accounts` | Lista plan de cuentas local |
| POST | `/api/v1/siigo/purchase-invoice-parameters` | Guarda plantilla para facturas de compra |
| GET  | `/api/v1/siigo/purchase-invoice-parameters` | Lista plantillas locales |
| GET  | `/health` | Health check |

### integration-config-service (:8007) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| PUT  | `/api/v1/integrations/credentials` | Crear/actualizar credenciales de integración |
| GET  | `/api/v1/integrations/credentials` | Lista credenciales (sin secretos) |
| POST | `/api/v1/integrations/cost-centers/imports` | Importa centros de costo desde .xlsx |
| POST | `/api/v1/integrations/chart-accounts/imports` | Importa plan de cuentas desde .xlsx |
| POST | `/api/v1/integrations/purchase-invoice-parameters` | Guarda plantilla proveedor-agnóstica |
| GET  | `/api/v1/integrations/purchase-invoice-parameters` | Lista plantillas (filtros: provider, account_key) |
| GET  | `/health` | Health check |

## Infraestructura

### PostgreSQL + pgvector
- Imagen: `pgvector/pgvector:pg16`
- La extensión `vector` se habilita automáticamente vía `scripts/init-db.sql`
- Driver: `psycopg2-binary`
- Tabla de vectores: `document_chunks` con columna `embedding Vector(768)`
- Búsqueda: operador coseno `<=>` de pgvector

### Ollama (embeddings locales)
- Imagen: `ollama/ollama` — contenedor `abacus_ollama`
- Modelo: `nomic-embed-text` (768 dimensiones, multilingual)
- El servicio `ollama-init` descarga el modelo automáticamente al primer `up`
- URL interna: `http://ollama:11434`

### Comunicación entre servicios
- **Protocolo**: HTTP síncrono con `httpx`
- `xml-processor` → `rag-service`: indexación best-effort (fallo no bloquea el XML)
- `llm-service` → `rag-service`: búsqueda semántica (fallo propaga excepción)

## Testing

Cada servicio tiene su propio directorio `tests/`.
- **xml-processor**: usa SQLite in-memory (conftest.py). Cubre xml_parser, zip_handler, dian_dv, smart_match, nit, repositorio de documentos.
- **rag-service**: mocks de repositorio y embedding service. No requiere PostgreSQL ni Ollama.
- **llm-service**: mocks de AIService y RagClient. No requiere OpenAI ni rag-service.

```bash
# Correr tests de rag-service
docker run --rm -v "$(pwd)/services/rag-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"

# Correr tests de llm-service
docker run --rm -v "$(pwd)/services/llm-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

## Variables de entorno (.env)

```
# PostgreSQL
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_USER=master
DATABASE_PASSWORD=master
DATABASE_NAME=xml2data

# OpenAI (llm-service)
OPENAI_API_KEY=sk-...

# Ollama (rag-service)
OLLAMA_HOST=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# URLs inter-servicio (sobreescritas en docker-compose)
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://llm-service:8003
XML_PROCESSOR_URL=http://xml-processor:8001

# Odoo (odoo-service)
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USER=admin
ODOO_PASSWORD=admin

# SIIGO (siigo-service)
SIIGO_BASE_URL=https://api.siigo.com
SIIGO_CHART_ACCOUNTS_PATH=/v1/accounts

# session-proxy
EXTERNAL_BASE_URL=https://catalogo-vpfe.dian.gov.co
EXTERNAL_LOGIN_PATH=/User/AuthToken
SESSION_TTL_SECONDS=3600

# Redis (session-proxy + xml-processor batch)
REDIS_URL=redis://redis:6379
```

## Reglas de desarrollo

### Documentación Swagger (obligatoria en todos los endpoints)

Cada endpoint FastAPI **debe** incluir:

```python
@router.post(
    "/ruta",
    response_model=MiResponse,
    status_code=201,
    summary="Título corto visible en la lista de endpoints",
    description=(
        "Descripción larga en markdown. Explicar:\n"
        "- Qué hace el endpoint.\n"
        "- Flujo interno si es relevante.\n"
        "- Reglas de negocio importantes.\n"
        "- Cuándo usar este endpoint vs otros similares."
    ),
    response_description="Qué retorna en caso exitoso.",
    responses={
        404: {"description": "Cuándo ocurre este error."},
        409: {"description": "Cuándo ocurre este error."},
    },
)
```

Cada DTO Pydantic **debe** documentar sus campos con `Field(description=..., examples=[...])`:

```python
class MiRequest(BaseModel):
    campo: str = Field(..., description="Para qué sirve este campo.", examples=["valor-ejemplo"])
    model_config = {
        "json_schema_extra": {"example": {"campo": "valor-ejemplo"}}
    }
```

**Acceso a la documentación:**
- **Centralizada (gateway):** `http://localhost:8000/docs` — selector de servicio en la parte superior
- Por servicio (desarrollo): `http://localhost:800{1,2,3}/docs`

Los specs OpenAPI de cada servicio también se exponen en el gateway:
- `http://localhost:8000/openapi/xml-processor.json`
- `http://localhost:8000/openapi/llm-service.json`
- `http://localhost:8000/openapi/rag-service.json`
- `http://localhost:8000/openapi/session-proxy.json`
- `http://localhost:8000/openapi/odoo-service.json`
- `http://localhost:8000/openapi/siigo-service.json`
- `http://localhost:8000/openapi/integration-config-service.json`

---

## Decisiones de diseño

- **Hexagonal por servicio**: cada microservicio tiene su propio dominio, puertos y adaptadores. No se comparte código entre servicios.
- **Best-effort en indexación**: si el rag-service no está disponible al procesar un XML, el xml-processor loguea un warning y continúa. La factura se guarda igual.
- **Best-effort en causación**: si el llm-service no está disponible tras procesar un ZIP, se loguea warning y el documento queda guardado. Se puede re-generar manualmente con `POST /api/v1/accounting/generate`.
- **Dominio independiente**: las entidades de dominio no se comparten entre servicios. Cada uno define sus propios contratos.
- **pgvector nativo**: la búsqueda vectorial usa el operador `<=>` directamente en SQL para máximo rendimiento.
- **Ollama en contenedor separado**: permite cambiar el modelo de embeddings sin tocar el código de rag-service (solo variable `OLLAMA_EMBED_MODEL`).
