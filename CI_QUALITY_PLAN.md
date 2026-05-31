# Plan: Esquema completo de calidad CI/CD para AbacusPlus API

> **Rama principal del repo: `master`** (no `main`). Todos los triggers, branch
> protection y workflows que referencien la rama principal deben usar `master`.

## Estado de ejecución

Marca cada casilla al completar la fase. Sirve como punto de retoma entre sesiones.

- [x] **Fase 0** — `pyproject.toml` raíz + base de archivos compartidos
- [x] **Fase 1** — Lint y formato (`ruff`) → `.github/workflows/01-lint.yml`
- [x] **Fase 2** — Seguridad (`bandit` + `pip-audit` + `semgrep`) → `02-security.yml`
- [x] **Fase 3** — PR checks + branch protection + coverage gate → `03-pr-checks.yml`
- [x] **Fase 4** — Unit tests en pipeline → `04-tests.yml`
- [ ] **Fase 5** — Contract tests (Schemathesis) → `05-contract-tests.yml`
- [ ] **Fase 6** — Component tests (respx + Postgres real) → `06-component-tests.yml`
- [ ] **Fase 7** — E2E mínimos (docker compose en runner) → `07-e2e.yml`

### Bitácora por fase

Anotar fecha, commit/PR y observaciones cuando se complete cada fase.

| Fase | Fecha | Commit / PR | Notas |
|---|---|---|---|
| 0 | 2026-05-30 | feature/implement_ci | pyproject.toml + .pre-commit-config.yaml creados |
| 1 | 2026-05-30 | feature/implement_ci | 01-lint.yml creado; ruff clean (158 archivos formateados, 9 errores suprimidos con noqa/contextlib.suppress) |
| 2 | 2026-05-30 | feature/implement_ci | 02-security.yml creado; python-dotenv→1.2.2 y cryptography→>=46.0.5 en 9 servicios; pytest CVE ignorado (pytest 9.x pendiente validación) |
| 3 | 2026-05-30 | feature/implement_ci | 03-pr-checks.yml + CODEOWNERS + dependabot + PR template + docs/branch-protection.md + scripts de cobertura |
| 4 | 2026-05-30 | feature/implement_ci | 04-tests.yml creado; 5 servicios en matriz (auth excluido sin tests); pytest.ini añadido a accounting-rules-service |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |

---

## Contexto

Monorepo Python con 10 microservicios (9 FastAPI + 1 NGINX gateway) sin ningún
workflow de CI escrito, sin herramientas de lint/format/seguridad instaladas, y
con 126 tests existentes (pytest + pytest-asyncio) en 5 de 9 servicios Python.

Objetivo: construir un pipeline de calidad por fases (lint → seguridad → PR
checks → unit → contract → component → E2E) que no rompa lo que ya funciona,
sea independiente por fase, ejecute lo más rápido posible en las primeras dos
fases (<2 min) y aproveche el OpenAPI ya expuesto por FastAPI.

## Decisiones clave (confirmadas)

| Decisión | Elección |
|---|---|
| Lint + format | `ruff` (única herramienta) |
| Seguridad código | `bandit` |
| Seguridad deps | `pip-audit` |
| OWASP API rules | `semgrep` con `p/owasp-top-ten` + `p/python` |
| Cobertura | umbral = cobertura actual −10 pp por servicio (medido en Fase 4 antes de activar gate) |
| Contract tests | Schemathesis sobre `/openapi.json` de cada servicio |
| Component tests | `respx` (httpx async mock) + Postgres real en `services:` del workflow |
| E2E | `docker compose up` en runner (advertencia: stack pesado, ver Fase 7) |
| Pre-commit | Opcional local (`.pre-commit-config.yaml`) |
| Matriz Python | 3.9 + 3.11 (refleja Dockerfiles reales) |
| Severidad bloqueante | bandit ≥ MEDIUM/HIGH confidence; pip-audit HIGH/CRITICAL; semgrep ERROR |
| **Rama principal** | **`master`** |

## Estructura de archivos a crear

```
api/
├── pyproject.toml                      # NUEVO — config raíz: ruff, bandit, pytest, coverage
├── .pre-commit-config.yaml             # NUEVO — hooks opcionales locales
├── CI_QUALITY_PLAN.md                  # este archivo
├── .github/
│   ├── CODEOWNERS                      # NUEVO
│   ├── dependabot.yml                  # NUEVO
│   ├── pull_request_template.md        # NUEVO
│   └── workflows/
│       ├── 01-lint.yml                 # NUEVO — Fase 1
│       ├── 02-security.yml             # NUEVO — Fase 2
│       ├── 03-pr-checks.yml            # NUEVO — Fase 3 (orquesta + size + coverage gate)
│       ├── 04-tests.yml                # NUEVO — Fase 4
│       ├── 05-contract-tests.yml       # NUEVO — Fase 5
│       ├── 06-component-tests.yml      # NUEVO — Fase 6
│       └── 07-e2e.yml                  # NUEVO — Fase 7
├── docs/
│   └── branch-protection.md            # NUEVO — instrucciones GitHub paso a paso (rama master)
├── tests/
│   ├── contract/                       # NUEVO — schemathesis suites
│   │   ├── conftest.py
│   │   └── test_<service>_contract.py
│   ├── component/                      # NUEVO — por servicio, respx + Postgres real
│   │   └── <service>/test_*.py
│   └── e2e/                            # NUEVO — 2 flujos contra gateway:8000
│       ├── conftest.py
│       ├── test_upload_xml_flow.py
│       └── test_approve_rule_flow.py
└── scripts/
    ├── measure_baseline_coverage.py    # NUEVO — corre pytest-cov por servicio,
    │                                    # emite mapa {service: pct} para fijar umbrales
    └── check_coverage_against_baseline.py  # NUEVO — usado por coverage-gate
```

Adiciones por servicio (`services/*/requirements.txt`):
```
pytest-cov==5.0.0
respx==0.21.1            # solo componentes que lo necesitan
```
ruff/bandit/pip-audit/semgrep **no** se añaden a requirements: se instalan en
los workflows para no contaminar imágenes de producción.

---

## Fase 0 — Base compartida (prerrequisito)

Antes de la Fase 1 se crea `pyproject.toml` raíz para alojar la configuración
compartida de ruff, bandit, pytest y coverage. Esto evita duplicar config en cada
servicio.

**`pyproject.toml` (raíz, fusiona secciones de Fases 1, 2 y 4)**:
```toml
[tool.ruff]
target-version = "py39"
line-length = 100
extend-exclude = ["**/migrations/**", "**/__pycache__/**", ".venv"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "C4", "SIM", "ASYNC", "S"]
ignore = ["S101", "B008"]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["S", "B"]
"**/conftest.py" = ["S", "B"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.bandit]
exclude_dirs = ["tests", "**/tests", ".venv"]
skips = ["B101"]

[tool.coverage.run]
branch = true
source = ["app"]
omit = ["**/tests/**", "**/migrations/**", "**/__init__.py"]

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "raise NotImplementedError", "if TYPE_CHECKING:"]
```

**Criterio de éxito Fase 0**
- `pyproject.toml` existe en raíz y es parseable por ruff/bandit/coverage.
- Marcar casilla Fase 0 en la sección de estado.

---

## Fase 1 — Linting y formato

**`.github/workflows/01-lint.yml`**:
```yaml
name: 01 - Lint

on:
  push:
    branches: ['**']
  pull_request:

concurrency:
  group: lint-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ruff:
    name: ruff (lint + format check)
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install ruff==0.6.9
      - name: ruff check
        run: ruff check .
      - name: ruff format --check
        run: ruff format --check .
```

**Criterio de éxito Fase 1**
- Workflow corre <2 min en cada push y PR.
- Falla ante errores de lint o archivos sin formatear.
- Commit de limpieza inicial: `ruff check --fix . && ruff format .` aplicado antes de activar el gate.
- Marcar casilla Fase 1.

---

## Fase 2 — Seguridad estática

**`.github/workflows/02-security.yml`**:
```yaml
name: 02 - Security

on:
  push:
    branches: ['**']
  pull_request:

concurrency:
  group: security-${{ github.ref }}
  cancel-in-progress: true

jobs:
  bandit:
    name: bandit (SAST)
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install bandit==1.7.10
      - name: bandit scan (HIGH severity, HIGH confidence)
        run: bandit -r services/ -c pyproject.toml -ll -ii

  pip-audit:
    name: pip-audit (deps CVEs)
    runs-on: ubuntu-latest
    timeout-minutes: 5
    strategy:
      fail-fast: false
      matrix:
        service:
          - xml-processor
          - rag-service
          - llm-service
          - session-proxy
          - odoo-service
          - siigo-service
          - integration-config-service
          - auth-service
          - accounting-rules-service
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pip-audit==2.7.3
      - name: audit ${{ matrix.service }}
        run: pip-audit -r services/${{ matrix.service }}/requirements.txt --strict

  semgrep:
    name: semgrep (OWASP API rules)
    runs-on: ubuntu-latest
    timeout-minutes: 5
    container:
      image: returntocorp/semgrep:latest
    steps:
      - uses: actions/checkout@v4
      - run: semgrep ci --config p/owasp-top-ten --config p/python --severity ERROR
```

**Criterio de éxito Fase 2**
- 3 jobs en paralelo. Bandit y semgrep <2 min; pip-audit ≤5 min.
- Bandit bloquea solo en `HIGH` severity + `HIGH` confidence (`-ll -ii`).
- pip-audit bloquea ante cualquier CVE con fix disponible. Usar `--ignore-vuln GHSA-xxx` con justificación en PR si no hay fix.
- semgrep bloquea solo en findings `ERROR`.
- Marcar casilla Fase 2.

---

## Fase 3 — Code review automatizado y branch protection

**`docs/branch-protection.md`** — instrucciones manuales para GitHub UI:
1. Settings → Branches → Add rule → Branch name pattern: **`master`**.
2. Marcar **Require a pull request before merging** (mínimo 1 aprobación, dismiss stale reviews).
3. Marcar **Require status checks to pass before merging** y **Require branches to be up to date**. Status checks obligatorios:
   - `01 - Lint / ruff (lint + format check)`
   - `02 - Security / bandit (SAST)`
   - `02 - Security / pip-audit (deps CVEs)` (toda la matriz)
   - `02 - Security / semgrep (OWASP API rules)`
   - `04 - Tests / pytest (<service>)` por cada servicio con tests
   - `03 - PR Checks / coverage-gate`
4. Marcar **Require conversation resolution before merging**.
5. Marcar **Do not allow bypassing the above settings** (incluye admins).
6. Marcar **Require linear history**.

**`.github/CODEOWNERS`**:
```
* @ikbo-co/backend
services/gateway/                @ikbo-co/devops
.github/workflows/               @ikbo-co/devops
```

**`.github/dependabot.yml`** — 9 entradas de pip (una por servicio) + github-actions mensual.

**`.github/pull_request_template.md`** — checklist (qué cambia, tests, riesgos, breaking).

**`.github/workflows/03-pr-checks.yml`**:
```yaml
name: 03 - PR Checks

on:
  pull_request:
    types: [opened, synchronize, reopened, edited]

jobs:
  size-label:
    name: PR size
    runs-on: ubuntu-latest
    steps:
      - uses: pascalgn/size-label-action@v0.5.5
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          sizes: >
            {"0": "XS", "20": "S", "100": "M", "400": "L", "1000": "XL"}

  size-warn:
    name: PR size warning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Warn if diff > 400 lines
        run: |
          BASE=${{ github.event.pull_request.base.sha }}
          HEAD=${{ github.event.pull_request.head.sha }}
          LINES=$(git diff --shortstat $BASE..$HEAD | awk '{print $4+$6}')
          echo "PR diff lines: $LINES"
          if [ "$LINES" -gt 400 ]; then
            echo "::warning::PR excede 400 líneas ($LINES). Considera dividirlo."
          fi

  coverage-gate:
    name: coverage-gate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: actions/download-artifact@v4
        with: { pattern: coverage-*, merge-multiple: true, path: ./coverage }
      - run: pip install coverage==7.6.1
      - name: Compare against per-service baseline (baseline - 10pp)
        run: python scripts/check_coverage_against_baseline.py
```

**`scripts/measure_baseline_coverage.py`** — corre `pytest --cov=app --cov-report=json` por servicio, emite `.coverage-baseline.json`:
```json
{"xml-processor": 72, "rag-service": 65, "llm-service": 58}
```

**`scripts/check_coverage_against_baseline.py`** — lee baseline, descarga coverage por servicio desde artifacts, falla si `coverage[service] < baseline[service] - 10`.

**Criterio de éxito Fase 3**
- Branch protection aplicada sobre `master` (verificado por el owner).
- Cada PR muestra label automática y warning si >400 líneas.
- Coverage gate bloquea caídas >10 pp respecto al baseline.
- Marcar casilla Fase 3.

---

## Fase 4 — Unit tests en pipeline

**`.github/workflows/04-tests.yml`**:
```yaml
name: 04 - Tests

on:
  push:
    branches: ['**']
  pull_request:

jobs:
  unit:
    name: pytest (${{ matrix.service }} / py${{ matrix.python }})
    runs-on: ubuntu-latest
    timeout-minutes: 10
    strategy:
      fail-fast: false
      matrix:
        service:
          - xml-processor
          - rag-service
          - llm-service
          - session-proxy
          - accounting-rules-service
        python: ['3.9']
        include:
          - service: auth-service
            python: '3.11'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: 'pip'
          cache-dependency-path: services/${{ matrix.service }}/requirements.txt
      - run: pip install -r services/${{ matrix.service }}/requirements.txt pytest-cov==5.0.0
      - name: pytest with coverage
        working-directory: services/${{ matrix.service }}
        run: |
          python -m pytest tests/ \
            --cov=app --cov-report=xml --cov-report=term \
            --junitxml=junit.xml
        env:
          DATABASE_HOST: localhost
          DATABASE_PORT: '5432'
          DATABASE_USER: test
          DATABASE_PASSWORD: test
          DATABASE_NAME: test
          OPENAI_API_KEY: sk-test
          OLLAMA_HOST: http://localhost:11434
          OLLAMA_EMBED_MODEL: nomic-embed-text
          RAG_SERVICE_URL: http://localhost:8002
          LLM_SERVICE_URL: http://localhost:8003
          XML_PROCESSOR_URL: http://localhost:8001
          ACCOUNTING_RULES_SERVICE_URL: http://localhost:8009
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.service }}
          path: services/${{ matrix.service }}/coverage.xml
      - uses: dorny/test-reporter@v1
        if: always()
        with:
          name: ${{ matrix.service }} tests
          path: services/${{ matrix.service }}/junit.xml
          reporter: java-junit
```

Servicios con `tests/` vacío (`integration-config-service`, `odoo-service`, `siigo-service`) **no se incluyen** en la matriz hasta tener tests reales. Se documenta como deuda técnica en `docs/branch-protection.md`.

**Criterio de éxito Fase 4**
- 6 jobs en paralelo (`fail-fast: false`), cada uno <5 min.
- Coverage XML subido por servicio como artifact (consumido por Fase 3 gate).
- Reporte JUnit visible en cada PR vía `dorny/test-reporter`.
- Tests actuales pasan sin modificación.
- Marcar casilla Fase 4.

---

## Fase 5 — Contract tests (Schemathesis sobre OpenAPI)

Cada FastAPI ya expone `/openapi.json`. Schemathesis genera casos automáticos
contra ese spec. Se valida:
1. El productor (servidor) implementa lo que documenta.
2. Los consumidores (clientes httpx en otros servicios) llaman rutas/payloads válidos contra el spec del productor.

**Pares cubiertos**:
- xml-processor → rag-service (POST /chunks)
- xml-processor → llm-service (GET /accounting/entries/{id})
- xml-processor → accounting-rules-service (POST /rules/approvals)
- llm-service → rag-service (POST /chunks/search)
- llm-service → xml-processor (GET catalog, /documents, /issuers)
- llm-service → accounting-rules-service (POST /rules/lookups)
- odoo-service → rag-service (POST /chunks)

**`tests/contract/conftest.py`** — levanta cada servicio en background con uvicorn y expone fixtures con la URL local.

**`tests/contract/test_rag_service_contract.py`** (producer-side):
```python
import schemathesis

schema = schemathesis.from_uri("http://localhost:8002/openapi.json")

@schema.parametrize()
def test_api(case):
    case.call_and_validate()
```

**`tests/contract/test_xml_processor_consumes_rag.py`** (consumer-side):
```python
import schemathesis

rag_schema = schemathesis.from_uri("http://localhost:8002/openapi.json")

def test_index_chunk_matches_rag_contract():
    payload = {"content": "test", "document_id": 1, "metadata": {}}
    operation = rag_schema["/api/v1/chunks"]["POST"]
    case = operation.make_case(body=payload)
    case.validate()
```

**`.github/workflows/05-contract-tests.yml`**:
```yaml
name: 05 - Contract Tests

on:
  push:
    branches: ['**']
  pull_request:

jobs:
  contract:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: master
          POSTGRES_PASSWORD: master
          POSTGRES_DB: xml2data
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready -U master"
          --health-interval 10s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install schemathesis==3.36.0
      - name: Start producer services in background
        run: |
          for svc in xml-processor rag-service llm-service accounting-rules-service; do
            pip install -r services/$svc/requirements.txt -q
            (cd services/$svc && python -m uvicorn app.main:app --port ${PORTS[$svc]} &)
          done
          sleep 8
      - run: python -m pytest tests/contract/ -v
```

**Criterio de éxito Fase 5**
- Falla ante cualquier desviación productor ↔ spec (status codes, response schemas, query params).
- Falla si un cliente httpx envía payload que el OpenAPI del productor rechaza.
- Marcar casilla Fase 5.

---

## Fase 6 — Component tests

Cada servicio se prueba **completo** (API + casos de uso + repos) con externos mockeados:

| Servicio | Mocks externos | DB local | HTTP mocks |
|---|---|---|---|
| xml-processor | rag, llm, odoo, accounting-rules | Postgres real | respx |
| llm-service | OpenAI, rag, xml-processor, accounting-rules | — | respx + AsyncMock |
| rag-service | Ollama | Postgres + pgvector real | respx |
| accounting-rules-service | Ollama | Postgres + pgvector real | respx |
| odoo-service | Odoo XML-RPC, rag | Postgres real | unittest.mock para xmlrpc |
| siigo-service | SIIGO API | Postgres real | respx |
| session-proxy | DIAN portal, Redis | — | respx |
| integration-config-service | — | Postgres real | — |
| auth-service | — | Postgres + Redis real | — |

`respx` se elige sobre `responses` porque los clientes ya usan httpx async.

**`.github/workflows/06-component-tests.yml`**:
```yaml
name: 06 - Component Tests

on:
  push:
    branches: ['**']
  pull_request:

jobs:
  component:
    name: component (${{ matrix.service }})
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        service: [xml-processor, rag-service, llm-service, accounting-rules-service, siigo-service, integration-config-service, auth-service, odoo-service, session-proxy]
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: master
          POSTGRES_PASSWORD: master
          POSTGRES_DB: xml2data
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready -U master"
          --health-interval 10s --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ['6379:6379']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.service == 'auth-service' && '3.11' || '3.9' }}
          cache: 'pip'
      - run: pip install -r services/${{ matrix.service }}/requirements.txt respx==0.21.1 pytest-cov==5.0.0
      - run: python -m pytest tests/component/${{ matrix.service }}/ -v --cov=services/${{ matrix.service }}/app
        env:
          DATABASE_HOST: localhost
          DATABASE_PORT: '5432'
          DATABASE_USER: master
          DATABASE_PASSWORD: master
          DATABASE_NAME: xml2data
          REDIS_URL: redis://localhost:6379
```

**Criterio de éxito Fase 6**
- 1 job por servicio (9 en paralelo), <10 min cada uno.
- DB real responde correctamente; outbound httpx 100% mockeado.
- No requiere Ollama ni OpenAI ni SIIGO ni Odoo.
- Marcar casilla Fase 6.

---

## Fase 7 — E2E mínimos

### Advertencia sobre tamaño del stack
`docker compose` levanta: postgres (pgvector), redis, ollama (~4 GB imagen + ~280 MB modelo `nomic-embed-text`), gateway, 9 servicios Python. Runner `ubuntu-latest` (7 GB RAM, 14 GB disk) lo soporta al límite.

Mitigaciones:
- Cache de Ollama (`~/.ollama`) entre runs (ahorra ~80 s de pull).
- Omitir `odoo-service` y `siigo-service` del E2E (no participan en flujos críticos).
- `--scale session-proxy-worker=0` (no se necesita browser-worker para E2E mínimo).
- Si el runner queda corto de recursos, migrar a self-hosted runner (follow-up).

### Flujos cubiertos (2)
1. **Upload XML → consulta documento** — POST `/api/v1/documents` con ZIP de prueba → GET `/api/v1/documents/{id}/full` valida pipeline xml-processor → rag-service → llm-service.
2. **Approve documento → regla aprendida** — PATCH `/api/v1/documents/{id}/approve` → GET `/api/v1/rules?nit=...` valida que xml-processor notificó a accounting-rules-service.

**`tests/e2e/test_upload_xml_flow.py`**:
```python
import httpx, pathlib, time

GATEWAY = "http://localhost:8000"

def test_upload_xml_and_query(zip_fixture: pathlib.Path):
    with zip_fixture.open("rb") as f:
        r = httpx.post(f"{GATEWAY}/api/v1/documents", files={"file": f}, timeout=60)
    assert r.status_code == 201
    doc_id = r.json()["id"]

    time.sleep(3)  # indexación RAG best-effort

    full = httpx.get(f"{GATEWAY}/api/v1/documents/{doc_id}/full")
    assert full.status_code == 200
    assert full.json()["document"]["id"] == doc_id
```

**`.github/workflows/07-e2e.yml`**:
```yaml
name: 07 - E2E

on:
  pull_request:
    branches: [master]

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Cache Ollama model
        uses: actions/cache@v4
        with:
          path: ~/.ollama
          key: ollama-nomic-embed-text-v1
      - name: docker compose up
        run: |
          cp .env.example .env 2>/dev/null || true
          docker compose up -d --build database redis ollama
          docker compose up -d --build gateway xml-processor rag-service llm-service \
                                       accounting-rules-service auth-service \
                                       integration-config-service session-proxy
          docker compose ps
      - name: Wait for gateway health
        run: |
          for i in {1..60}; do
            curl -fsS http://localhost:8000/health && exit 0
            sleep 5
          done
          exit 1
      - run: pip install httpx==0.27.0 pytest==8.3.4
      - run: python -m pytest tests/e2e/ -v
        env:
          GATEWAY_URL: http://localhost:8000
      - name: Dump logs on failure
        if: failure()
        run: docker compose logs --tail=200
```

**Criterio de éxito Fase 7**
- Workflow corre **solo en PR a `master`**, no en push a otras ramas.
- 2 flujos pasan end-to-end contra el gateway.
- Si el runner queda sin memoria/disco se documenta migración a self-hosted runner.
- Marcar casilla Fase 7.

---

## Reutilización de código existente

- **`scripts/run_tests.py`** — se mantiene para desarrollo local; los workflows de CI no lo invocan (CI usa pytest directo para tener cache de pip por servicio). Mencionar en `docs/branch-protection.md` para devs.
- **`pytest.ini`** existentes (4 servicios) — se conservan; añadir el mismo contenido en los 5 restantes para uniformidad.
- **`conftest.py`** existentes — sin cambios; los workflows pasan las mismas env vars.
- **Clients en `services/*/app/infrastructure/clients/`** — usados tal cual por los contract tests de Fase 5 para validar consumer-side.

---

## Verificación end-to-end

Tras implementar las 7 fases:

1. **Fase 1** — abrir PR trivial (typo en README). `01-lint.yml` debe pasar verde en <2 min.
2. **Fase 2** — introducir deliberadamente `subprocess.call(input_str, shell=True)`. Bandit debe fallar.
3. **Fase 3** — abrir PR de 500 líneas: label `size/L` + warning. Reducir cobertura xml-processor 15 pp: coverage-gate debe fallar.
4. **Fase 4** — `pytest services/xml-processor/tests --cov=app` local debe coincidir con CI.
5. **Fase 5** — cambiar response model sin actualizar spec OpenAPI: schemathesis debe fallar.
6. **Fase 6** — `pytest tests/component/rag-service` local con `docker run pgvector/pgvector:pg16`.
7. **Fase 7** — abrir PR a `master`. Solo entonces corre `07-e2e.yml`.

## Orden de implementación recomendado

1. **Fase 0 + Fase 1 + Fase 2** (1 día) — feedback rápido prioritario.
2. Limpieza inicial: `ruff check --fix . && ruff format .` en commit dedicado.
3. **Fase 4** — unit tests al pipeline (1 día). Antes de Fase 3 para producir artifacts.
4. Medir baseline coverage con `scripts/measure_baseline_coverage.py`.
5. **Fase 3** — branch protection + coverage gate (medio día).
6. **Fase 6** — component tests (2 días, requiere escribir tests/component/).
7. **Fase 5** — contract tests con schemathesis (1 día).
8. **Fase 7** — E2E (1 día + observación de consumo de runner).
