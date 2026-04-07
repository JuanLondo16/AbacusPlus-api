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
                   ├─ POST /api/v1/readxml    ──►  xml-processor :8001
                   │  GET  /api/v1/documents        │  procesa ZIP/XML → PostgreSQL
                   │  GET  /api/v1/receivers         └─ POST /api/v1/chunks  ──►  rag-service :8002
                   │                                                                (indexa embedding)
                   │
                   ├─ POST /api/v1/query      ──►  llm-service :8003
                   │  POST /api/v1/ai/analyze        │  POST /api/v1/chunks/search ──► rag-service :8002
                   │                                 └─ OpenAI API (prompt RAG-aumentado)
                   │
                   └─ POST /api/v1/chunks     ──►  rag-service :8002  (debug/admin)
                      GET  /health/*
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
│   └── llm-service/            # Puerto 8003
│       ├── app/
│       │   ├── adapters/api/routers/   analyze.py · query.py
│       │   ├── application/use_cases/  analyze_with_ai.py · query_with_rag.py
│       │   ├── application/dto/        ai.py · query.py
│       │   ├── domain/ports/           services.py  (AIServicePort · RagClientPort)
│       │   └── infrastructure/
│       │       ├── ai/                 openai_service.py
│       │       ├── clients/            rag_client.py  ← HTTP client a rag-service
│       │       └── config/             logging.py
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
| POST | `/api/v1/readxml` | xml-processor |
| GET  | `/api/v1/documents/` | xml-processor |
| GET  | `/api/v1/documents/{id}` | xml-processor |
| GET  | `/api/v1/receivers` | xml-processor |
| POST | `/api/v1/query` | llm-service |
| POST | `/api/v1/ai/analyze` | llm-service |
| POST | `/api/v1/chunks` | rag-service |
| POST | `/api/v1/chunks/search` | rag-service |
| GET  | `/health` | gateway |
| GET  | `/health/xml-processor` | xml-processor |
| GET  | `/health/rag-service` | rag-service |
| GET  | `/health/llm-service` | llm-service |

### xml-processor (:8001) — interno
| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/readxml` | Procesa ZIP o XML DIAN |
| GET  | `/api/v1/documents/` | Lista documentos por rango de fechas |
| GET  | `/api/v1/documents/{id}` | Detalle de un documento |
| GET  | `/api/v1/receivers` | Lista receptores |
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
| POST | `/api/v1/ai/analyze` | Prompt directo a OpenAI sin RAG |
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

---

## Decisiones de diseño

- **Hexagonal por servicio**: cada microservicio tiene su propio dominio, puertos y adaptadores. No se comparte código entre servicios.
- **Best-effort en indexación**: si el rag-service no está disponible al procesar un XML, el xml-processor loguea un warning y continúa. La factura se guarda igual.
- **Best-effort en causación**: si el llm-service no está disponible tras procesar un ZIP, se loguea warning y el documento queda guardado. Se puede re-generar manualmente con `POST /api/v1/accounting/generate`.
- **Dominio independiente**: las entidades de dominio no se comparten entre servicios. Cada uno define sus propios contratos.
- **pgvector nativo**: la búsqueda vectorial usa el operador `<=>` directamente en SQL para máximo rendimiento.
- **Ollama en contenedor separado**: permite cambiar el modelo de embeddings sin tocar el código de rag-service (solo variable `OLLAMA_EMBED_MODEL`).
