"""Helpers compartidos para component tests."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{os.getenv('DATABASE_USER', 'master')}:{os.getenv('DATABASE_PASSWORD', 'master')}"
    f"@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5432')}"
    f"/{os.getenv('DATABASE_NAME', 'xml2data')}"
)


def make_test_engine(enable_vector: bool = False):
    engine = create_engine(TEST_DATABASE_URL)
    if enable_vector:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    return engine


def make_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
