# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the API locally (requires DB)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run with Docker (recommended for development)
docker-compose up --build

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/utils/test_xml_parser.py -v

# Run a single test
pytest tests/utils/test_xml_parser.py::test_function_name -v

# Install dependencies
pip install -r requirements.txt
```

## Architecture

This is a FastAPI microservice for parsing and storing DIAN (Colombian tax authority) electronic invoices (XML/ZIP format). It follows **Hexagonal Architecture** (Ports & Adapters):

```
app/
├── domain/          # Core business logic — no external dependencies
│   ├── entities/    # Pure dataclass entities (Document, Issuer, Receiver, Tax, Concept)
│   ├── value_objects/  # NIT with verification digit
│   ├── exceptions/  # Custom exception hierarchy
│   └── ports/repositories.py  # Abstract interfaces (ABC) — the "ports"
│
├── application/     # Use cases orchestrate domain logic
│   ├── use_cases/   # ProcessXmlUseCase, query use cases
│   └── dto/         # Pydantic v2 response models
│
├── infrastructure/  # "Adapters" for external systems
│   ├── persistence/
│   │   ├── models/       # SQLAlchemy ORM models (MySQL 8.0)
│   │   └── repositories/ # Concrete repository implementations
│   └── config/           # database.py (SQLAlchemy 2.0), logging.py
│
├── adapters/api/    # HTTP input adapters
│   └── routers/     # xml.py, documents.py, receivers.py
│
├── utils/           # xml_parser.py, zip_handler.py, dian_dv.py, smart_match.py
├── dependencies.py  # Composition root — wires all DI via FastAPI Depends()
└── main.py          # App setup, router registration, exception handlers
```

### Dependency Flow

`Router → Use Case → Repository Port (ABC) → Repository Implementation`

`dependencies.py` is the composition root where all concrete implementations are wired together and injected via FastAPI's `Depends()`.

### Key Design Decisions

- **"Ensure exists" pattern**: Issuer, Receiver, and Tax records are created on first encounter during XML processing, not pre-registered.
- **Smart concept matching**: Invoice line descriptions are normalized using a hybrid 40% Levenshtein + 60% TF-IDF cosine similarity algorithm (`utils/smart_match.py`) with an 80% threshold to match against `ConceptDescription` records per receiver.
- **Domain exceptions → HTTP codes**: `app/adapters/api/error_handlers.py` maps domain exceptions to HTTP status codes via `STATUS_MAP`. New exception types should be added there.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/readxml` | Upload and process a DIAN XML or ZIP invoice |
| GET | `/api/v1/documents/` | List documents by date range (`dateini`, `datefin` params) |
| GET | `/api/v1/documents/{id}` | Get document with full details |
| GET | `/api/v1/receivers` | List all receivers |

### XML Parsing Reference

`samples/xml/` contains 8 real DIAN invoice samples covering distinct parsing scenarios (mixed IVA, discounts, bag tax, withholding taxes, public utilities, no-IVA, many lines, etc.). See [`samples/xml/README.md`](samples/xml/README.md) before modifying `app/utils/xml_parser.py` — it documents the structural differences between scenarios (which elements are absent, non-standard tax schemes, `unitCode` variants, etc.).

### Testing

Tests use an in-memory SQLite DB (via `tests/conftest.py` `db_session` fixture). `pytest.ini` sets `asyncio_mode = auto`. Test files mirror the `app/` structure under `tests/`.

### Environment Variables

Required in `.env` (see existing `.env` for values):
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`
