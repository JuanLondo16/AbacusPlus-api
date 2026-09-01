import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, root)

# Las variables de entorno deben existir antes de importar cualquier módulo de app.
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "test")
os.environ.setdefault("DATABASE_PASSWORD", "test")
os.environ.setdefault("DATABASE_NAME", "test")
