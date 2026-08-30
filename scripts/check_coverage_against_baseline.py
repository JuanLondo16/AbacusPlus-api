#!/usr/bin/env python3
"""
Compara la cobertura actual (artifacts de CI) contra el baseline guardado.
Falla si algún servicio bajó más de 10 puntos porcentuales.

Uso en CI:
  python scripts/check_coverage_against_baseline.py

Espera encontrar:
  - .coverage-baseline.json  en la raíz del repo
  - coverage/<servicio>/coverage.xml  descargados por actions/download-artifact
"""

import sys
from pathlib import Path

# defusedxml en vez de xml.etree: aunque el coverage.xml lo genera el propio CI (entrada
# confiable), usar el parser endurecido no cuesta nada y evita el falso positivo recurrente
# del análisis estático sobre este script.
import defusedxml.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = ROOT / ".coverage-baseline.json"
COVERAGE_DIR = ROOT / "coverage"
THRESHOLD_DROP = 10.0


def read_baseline() -> dict[str, float]:
    import json

    if not BASELINE_FILE.exists():
        print("No se encontró .coverage-baseline.json — saltando gate de cobertura")
        sys.exit(0)
    return json.loads(BASELINE_FILE.read_text())


def read_current(service: str) -> float | None:
    xml_path = COVERAGE_DIR / f"coverage-{service}" / "coverage.xml"
    if not xml_path.exists():
        # intenta ruta plana (merge-multiple: true)
        xml_path = COVERAGE_DIR / "coverage.xml"
    if not xml_path.exists():
        return None
    tree = ET.parse(xml_path)  # noqa: S314
    root = tree.getroot()
    line_rate = float(root.attrib.get("line-rate", 0))
    return round(line_rate * 100, 1)


def main() -> None:
    baseline = read_baseline()
    failures: list[str] = []

    for service, base_pct in baseline.items():
        current = read_current(service)
        if current is None:
            print(f"  {service}: sin artifact de cobertura — omitido")
            continue
        drop = base_pct - current
        status = "OK" if drop <= THRESHOLD_DROP else "FALLO"
        print(
            f"  {service}: baseline={base_pct}%  actual={current}%  caída={drop:.1f}pp  [{status}]"
        )
        if drop > THRESHOLD_DROP:
            failures.append(f"{service}: bajó {drop:.1f}pp (límite {THRESHOLD_DROP}pp)")

    if failures:
        print("\nCobertura insuficiente:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nCobertura dentro del límite.")


if __name__ == "__main__":
    main()
