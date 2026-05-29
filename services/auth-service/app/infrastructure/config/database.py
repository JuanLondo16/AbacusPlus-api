import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

_engine = None
_SessionLocal = None


def _build_url() -> str:
    return (
        f"postgresql+psycopg2://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}"
        f"@{os.environ['DATABASE_HOST']}:{os.environ.get('DATABASE_PORT', '5432')}"
        f"/{os.environ.get('DATABASE_NAME', 'abacus_meta')}"
    )


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(_build_url(), pool_pre_ping=True)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_db():
    get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
