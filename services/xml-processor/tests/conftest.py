import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set env vars before importing any app module
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "test")
os.environ.setdefault("DATABASE_PASSWORD", "test")
os.environ.setdefault("DATABASE_NAME", "test")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for tests."""
    import app.infrastructure.persistence.models.concept  # noqa: F401

    # Import all models to register tables in Base.metadata
    import app.infrastructure.persistence.models.document  # noqa: F401
    import app.infrastructure.persistence.models.integration_cost_center  # noqa: F401
    import app.infrastructure.persistence.models.integration_payment_type  # noqa: F401
    import app.infrastructure.persistence.models.integration_tax  # noqa: F401
    import app.infrastructure.persistence.models.issuer  # noqa: F401
    import app.infrastructure.persistence.models.receiver  # noqa: F401
    import app.infrastructure.persistence.models.tax  # noqa: F401
    from app.infrastructure.config.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
