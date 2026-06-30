"""
Fixtures compartidos para los contract tests.

Cada fixture levanta el servicio correspondiente en background
con uvicorn y espera a que responda en /health.
"""

import subprocess
import sys
import time

import httpx
import pytest


def _wait_for_service(url: str, timeout: int = 30) -> bool:
    for _ in range(timeout):
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _start_service(service: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--host", "0.0.0.0"],
        cwd=f"services/{service}",
    )
    return proc


@pytest.fixture(scope="session")
def rag_service_url():
    port = 18002
    proc = _start_service("rag-service", port)
    url = f"http://localhost:{port}"
    if not _wait_for_service(f"{url}/health"):
        proc.terminate()
        pytest.skip("rag-service no arrancó en tiempo")
    yield url
    proc.terminate()


