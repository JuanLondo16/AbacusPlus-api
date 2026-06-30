#!/usr/bin/env python3
"""
Mide la cobertura actual de cada servicio y guarda el resultado en .coverage-baseline.json.

Uso:
  python scripts/measure_baseline_coverage.py

El archivo generado es leído por check_coverage_against_baseline.py para saber
cuánto puede bajar la cobertura antes de bloquear un PR (umbral = baseline - 10 pp).
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SERVICES = [
    "xml-processor",
    "rag-service",
    "llm-service",
    "session-proxy",
]

BASELINE_FILE = ROOT / ".coverage-baseline.json"


def measure(service: str) -> float | None:
    svc_path = ROOT / "services" / service
    result = subprocess.run(  # noqa: S603
        [
            sys.executable, "-m", "pytest", "tests/",
            "--cov=app", "--cov-report=json",
            "-q", "--tb=no",
        ],
        cwd=svc_path,
        capture_output=True,
        text=True,
    )
    coverage_json = svc_path / "coverage.json"
    if coverage_json.exists():
        data = json.loads(coverage_json.read_text())
        pct = round(data["totals"]["percent_covered"], 1)
        coverage_json.unlink()
        return pct
    print(f"  [{service}] sin coverage.json — pytest salió con código {result.returncode}")
    return None


def main() -> None:
    baseline: dict[str, float] = {}
    for svc in SERVICES:
        print(f"Midiendo {svc}...")
        pct = measure(svc)
        if pct is not None:
            baseline[svc] = pct
            print(f"  {svc}: {pct}%")
        else:
            print(f"  {svc}: omitido")

    BASELINE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"\nBaseline guardado en {BASELINE_FILE}")
    print(json.dumps(baseline, indent=2))


if __name__ == "__main__":
    main()
