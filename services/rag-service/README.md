# rag-service

Puerto: **8002**

## Responsabilidad

Indexa fragmentos de texto con embeddings vectoriales y sirve busquedas por similitud coseno. Es la capa de recuperacion del sistema RAG (Retrieval-Augmented Generation).

No genera texto. No llama a OpenAI. No conoce el formato DIAN ni la logica contable.

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| POST | `/api/v1/chunks` | Indexa un fragmento de texto: genera embedding con Ollama y lo guarda en PostgreSQL (201) |
| POST | `/api/v1/chunks/search` | Busqueda semantica top-k por similitud coseno sobre los chunks indexados |
| GET | `/health` | Health check |

**POST /api/v1/chunks** — llamado automaticamente por xml-processor tras procesar cada factura. Retorna 502 si Ollama no esta disponible.

**POST /api/v1/chunks/search** — llamado por llm-service para construir el contexto RAG antes de llamar a OpenAI. El score de similitud va de `0.0` (sin relacion) a `1.0` (identico). Retorna 502 si Ollama no esta disponible.

## Dependencias internas

| Servicio | URL | Proposito |
|---------|-----|-----------|
| Ollama | `OLLAMA_HOST` (por defecto `http://ollama:11434`) | Genera embeddings con el modelo `nomic-embed-text` (768 dimensiones) |
| PostgreSQL + pgvector | `DATABASE_*` | Almacena chunks y vectores; ejecuta busquedas con operador coseno `<=>` |

## Variables de entorno

```
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_USER=master
DATABASE_PASSWORD=master
DATABASE_NAME=abacus

OLLAMA_HOST=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
```

## Tests

```bash
docker run --rm -v "$(pwd)/services/rag-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```

Los tests usan mocks del repositorio y del embedding service. No requieren PostgreSQL ni Ollama.

## Decisiones de diseno

- **pgvector con operador coseno (`<=>`):** la busqueda de similitud ocurre directamente en SQL, mas eficiente que calcular distancias en Python sobre vectores cargados en memoria.
- **Texto truncado antes de enviar a Ollama:** el contenido se recorta a ~3500 caracteres para no exceder el contexto del modelo; el espanol genera mas tokens que el ingles para el mismo texto.
- **Sin autenticacion interna:** el servicio solo es accesible desde la red Docker. No implementa tokens ni API keys propios.
- **Modelo intercambiable:** cambiar `OLLAMA_EMBED_MODEL` permite usar otro modelo de embeddings sin tocar el codigo, siempre que la dimension de salida coincida con el esquema de la tabla (`Vector(768)`).
