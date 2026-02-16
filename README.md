# XML Reader API

FastAPI microservice for processing Colombian DIAN electronic invoices (XML/ZIP). Extracts invoice data, manages issuers, receivers, taxes, and concept matching.

## Architecture

Hexagonal architecture (Ports & Adapters):

```
app/
├── domain/           # Core business logic (no external dependencies)
│   ├── entities/     # Pure dataclass entities
│   ├── value_objects/ # NIT with verification digit
│   ├── exceptions/   # Domain exception hierarchy
│   └── ports/        # Abstract interfaces (repositories, services)
├── application/      # Use cases and DTOs
│   ├── use_cases/    # ProcessXml, ManageUsers, QueryDocuments, QueryReceivers
│   └── dto/          # Pydantic v2 request/response models
├── infrastructure/   # External adapters (output)
│   ├── persistence/  # SQLAlchemy models and repository implementations
│   ├── auth/         # Password hashing (bcrypt) and JWT service
│   └── config/       # Database and logging configuration
├── adapters/         # Input adapters
│   └── api/          # FastAPI routers and error handlers
├── utils/            # XML parsing, ZIP extraction, text matching
├── dependencies.py   # Composition root (DI wiring)
└── main.py           # FastAPI application entry point
```

## Setup

### Prerequisites

- Python 3.9+
- MySQL 8.0
- Docker & Docker Compose (optional)

### Environment Variables

Create a `.env` file:

```env
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_USER=root
DATABASE_PASSWORD=
DATABASE_NAME=xml_reader_db
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker-compose up --build
```

## Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Welcome message |
| GET | `/health` | Health check |
| POST | `/api/v1/readxml` | Process a DIAN XML/ZIP invoice |
| POST | `/api/v1/users/` | Create a new user |
| POST | `/api/v1/login` | Authenticate and get JWT cookie |
| GET | `/api/v1/documents/` | List documents by date range |
| GET | `/api/v1/documents/{id}` | Get document by ID |
| GET | `/api/v1/receivers` | List all receivers |

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy** - ORM
- **Pydantic v2** - Data validation
- **MySQL** - Database
- **JWT** - Authentication
- **lxml** - XML parsing
- **scikit-learn + Levenshtein** - Concept text matching
