import logging
import os
from contextlib import asynccontextmanager

import psycopg2
from fastapi import FastAPI

from app.adapters.api.routers import auth, tenants, users
from app.infrastructure.config.database import Base, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _ensure_meta_db_exists() -> None:
    conn = psycopg2.connect(
        host=os.environ["DATABASE_HOST"],
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        user=os.environ["DATABASE_USER"],
        password=os.environ["DATABASE_PASSWORD"],
        dbname="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = 'abacus_meta'")
            if cur.fetchone() is None:
                cur.execute("CREATE DATABASE abacus_meta")
                logger.info("Created database abacus_meta")
            else:
                logger.info("abacus_meta already exists")
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    internal_secret = os.environ.get("INTERNAL_SECRET", "")
    if not internal_secret or internal_secret == "change-me":
        raise RuntimeError(
            "INTERNAL_SECRET no está configurado (o sigue en 'change-me' de .env.example). "
            "auth-service lo usa para autenticar cada llamada de aprovisionamiento a los "
            "demás microservicios al crear un tenant. Genera uno real: openssl rand -hex 32"
        )
    _ensure_meta_db_exists()
    Base.metadata.create_all(bind=get_engine(), checkfirst=True)
    logger.info("auth-service started")
    yield


app = FastAPI(
    title="Auth Service",
    description="Gestion de tenants, usuarios y tokens JWT RS256 para AbacusPlus.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(users.router)


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok", "service": "auth-service"}
