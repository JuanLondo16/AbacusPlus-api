import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set env vars before importing any app module
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "3306")
os.environ.setdefault("DATABASE_USER", "test")
os.environ.setdefault("DATABASE_PASSWORD", "test")
os.environ.setdefault("DATABASE_NAME", "test")


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for tests."""
    from app.infrastructure.config.database import Base
    # Import all models to register tables in Base.metadata
    import app.infrastructure.persistence.models.document  # noqa: F401
    import app.infrastructure.persistence.models.issuer  # noqa: F401
    import app.infrastructure.persistence.models.receiver  # noqa: F401
    import app.infrastructure.persistence.models.tax  # noqa: F401
    import app.infrastructure.persistence.models.concept  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
