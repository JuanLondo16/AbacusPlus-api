# Plan: Refactorización Modelo Contable — Asignación de Cuentas por Ítem

## Context

El sistema actualmente genera asientos contables completos (débitos/créditos balanceados) vía LLM. El nuevo diseño simplifica el rol del LLM: solo asigna cuentas PUC por ítem de detalle. Los asientos completos quedan para el software contable de destino (SIIGO/Odoo). El historial de asignaciones vive en `document_details.code`, eliminando la necesidad del accounting-rules-service.

---

## Hallazgos Clave de la Auditoría

- **documents** tiene `accounting_entry_id` (eliminar) pero no `payment_type_id` (agregar)
- **issuers** ya tiene `payment_id` FK → `integration_payment_types.id` ✅
- **document_details** no tiene `type`, `code`, `tax_id`, `cost_center_id` (agregar los 4)
- **integration_taxes**: `id, name (unique), type, percentage (Numeric10,4), active`
- **integration_cost_centers**: `id, code (unique), name, external_id, active` — los campos `provider` y `account_key` **serán eliminados** (ver Fase 0)
- **Arquitectura multi-tenant**: cada tenant tiene su propia base de datos `abacus_t_{slug}`. La DB por defecto de desarrollo debe llamarse `abacus` (no `xml2data`). Todas las tablas de un mismo tenant viven en la misma base → FK reales entre servicios son válidas dentro del mismo tenant.
- **Sin Alembic** — migraciones vía SQL imperativo en `_migrate_tenant_db()` dentro de `internal.py` de cada servicio; se aplican llamando `POST /internal/provision-tenant?tenant_slug={slug}`
- **accounting-rules-service**: solo lo consumen llm-service (lookups) y xml-processor (approvals) — eliminable

---

## Cómo aplicar cambios de BD

> Esta sección aplica a **todas las fases** que incluyan `ALTER TABLE`.

El sistema no usa Alembic. El esquema se gestiona así:

1. **Agregar los `ALTER TABLE` a `_migrate_tenant_db()`** en `services/{servicio}/app/adapters/api/routers/internal.py` de cada servicio afectado. Usar `IF EXISTS` / `IF NOT EXISTS` para que sea idempotente.
2. **Reconstruir la imagen Docker** del servicio afectado:
   ```bash
   docker-compose up --build {nombre-servicio}
   ```
3. **Para cada tenant existente**, llamar el endpoint de provisión con el header de seguridad:
   ```bash
   curl -X POST "http://localhost:800{puerto}/internal/provision-tenant?tenant_slug={slug}" \
        -H "X-Internal-Secret: {INTERNAL_SECRET}"
   ```
   Esto ejecuta `_migrate_tenant_db()` sobre la base `abacus_t_{slug}`.
4. **La DB de desarrollo** (`abacus`) se migra automáticamente al arrancar el servicio, porque el lifespan en `main.py` también llama `_migrate_tenant_db()` con el engine por defecto.

> Los servicios afectados en este plan: **xml-processor** (Fase 3) e **integration-config-service** (Fase 0).

---

## Checklist de Ejecución

### Fase 0 — Simplificar integration_cost_centers (integration-config-service) ✅

> Eliminar `provider` y `account_key` del modelo. El concepto de multi-proveedor de centros de costo no se usa; hardcodeaba `"default"/"default"` en todo el código.

**Modelo:** `services/integration-config-service/app/infrastructure/persistence/models/cost_center.py`
- [x] Eliminar columna `provider`
- [x] Eliminar columna `account_key`
- [x] Reemplazar `UniqueConstraint("provider", "account_key", "code", name="uq_cost_center_provider_key_code")` → `UniqueConstraint("code", name="uq_cost_center_code")`

**Repositorio:** `services/integration-config-service/app/infrastructure/persistence/repositories/cost_center_repository.py`
- [x] `upsert_many(provider, account_key, cost_centers)` → `upsert_many(cost_centers)`
- [x] `list(provider, account_key, active)` → `list(active=None)`

**Use case:** `services/integration-config-service/app/application/use_cases/import_cost_centers.py`
- [x] Eliminar constantes `_DEFAULT_PROVIDER = "default"` y `_DEFAULT_ACCOUNT_KEY = "default"`
- [x] Simplificar llamadas a `repository.upsert_many(cost_centers)` y `repository.list()`

**Router:** `services/integration-config-service/app/adapters/api/routers/cost_centers.py`
- [x] Eliminar imports de `_DEFAULT_ACCOUNT_KEY`, `_DEFAULT_PROVIDER`
- [x] Simplificar llamadas a `repository.list(active=active)`

**Migración SQL** — `services/integration-config-service/app/adapters/api/routers/internal.py`
- [x] Función `_migrate_tenant_db()` creada con las 4 sentencias ALTER TABLE
- [x] `main.py` actualizado para llamar `_migrate_tenant_db(engine)` en el lifespan
- [ ] Reconstruir imagen y provisionar tenants (ver sección "Cómo aplicar cambios de BD")

---

### Fase 1 — Modelo SQLAlchemy: document.py (xml-processor) ✅
**Archivo:** `services/xml-processor/app/infrastructure/persistence/models/document.py`
- [x] Eliminar `accounting_entry_id` de `Document`
- [x] Agregar `payment_type_id = Column(Integer, ForeignKey("integration_payment_types.id"), nullable=True)` a `Document`
- [x] Agregar a `DocumentDetail`:
  - [x] `code = Column(String(50), nullable=True)`
  - [x] `type = Column(String(20), nullable=False, default="Account")`
  - [x] `tax_id = Column(Integer, ForeignKey("integration_taxes.id"), nullable=True)`
  - [x] `cost_center_id = Column(Integer, ForeignKey("integration_cost_centers.id"), nullable=True)`

### Fase 2 — Entidades de Dominio (xml-processor) ✅
**Archivo:** `services/xml-processor/app/domain/entities/document.py`
- [x] Eliminar `accounting_entry_id` de entidad `Document`
- [x] Agregar `payment_type_id: Optional[int] = None` a entidad `Document`
- [x] Agregar a entidad `DocumentDetail`:
  - [x] `code: Optional[str] = None`
  - [x] `type: str = "Account"`
  - [x] `tax_id: Optional[int] = None`
  - [x] `cost_center_id: Optional[int] = None`

### Fase 3 — Migración SQL (xml-processor) ✅
**Archivo:** `services/xml-processor/app/adapters/api/routers/internal.py` — función `_migrate_tenant_db()`
- [x] Agregar 6 sentencias ALTER TABLE al bloque `with engine.connect() as conn`
- [ ] Reconstruir imagen y provisionar tenants (ver sección "Cómo aplicar cambios de BD")

### Fase 4 — HTTP Client: IntegrationConfigClient (xml-processor) ✅
**Nuevo archivo:** `services/xml-processor/app/infrastructure/clients/integration_config_client.py`
- [x] Método `async get_taxes() -> list[dict]` → `GET /api/v1/integrations/taxes?active=true`
- [x] Timeout 5s, best-effort (retorna `[]` en fallo)
- [x] Registrar en `dependencies.py` — factory `get_integration_config_client`
- [x] Inyectar en `get_process_xml_use_case`

### Fase 5 — Lógica de Enriquecimiento en process_xml.py ✅
**Archivos modificados:**
- `services/xml-processor/app/application/use_cases/process_xml.py`
- `services/xml-processor/app/infrastructure/persistence/repositories/document_repository.py`

**payment_type_id:**
- [x] `_ensure_issuer` ahora retorna el `Issuer`; `issuer.payment_id` se pasa a `_build_document`

**tax_id (por cada detail):**
- [x] Fetch taxes al inicio de `execute()` (best-effort, una sola llamada)
- [x] `_match_tax(tax_type_str, taxes)`: match por `name` (case-insensitive) → match por `percentage` (±0.01) → warning + None
- [x] Si `tax_type in ("0", "", "0.00", "0.0")` → `tax_id = None` sin búsqueda

**cost_center_id (por cada detail):**
- [x] `DocumentRepository.find_most_frequent_cost_center(issuer_nit, description)` — ILIKE con primera palabra significativa + Counter.most_common(1)
- [x] Sin resultado → `cost_center_id = None`

### Fase 6 — Nuevo Endpoint PATCH /documents/{id}/details (xml-processor) ✅
- [x] DTOs: `DocumentDetailCodeUpdateItem`, `DocumentDetailCodeUpdateResponse` en `dto/document.py`
- [x] `DocumentRepository.update_detail_codes(assignments)` — bulk UPDATE por detail_id
- [x] `get_document_repo` factory en `dependencies.py`
- [x] `PATCH /api/v1/documents/{document_id}/details` en router — valida documento existe, ignora IDs inexistentes, Swagger completo

### Fase 7 — Actualizar GET /documents/{id}/full (xml-processor) ✅
- [x] `get_document_detail.py`: eliminados OdooClient y LlmClient, retorna documento directamente
- [x] `DocumentDetailResponse`: agregados `code`, `type`, `tax_id`, `cost_center_id` con Field docs
- [x] `DocumentResponse`: reemplazado `accounting_entry_id` por `payment_type_id`
- [x] `DocumentSummaryResponse`: reemplazado `accounting_entry_id` por `payment_type_id`
- [x] Router `/full`: simplificado, retorna `DocumentResponse` con details enriquecidos
- [x] `get_document_detail_use_case` en `dependencies.py`: eliminados odoo_client y llm_client

### Fase 8 — Limpieza approve_document.py (xml-processor) ✅
- [x] `approve_document.py`: eliminados `_notify_rules_service`, `llm_client`, `accounting_rules_client`; use case vuelve a ser síncrono
- [x] `dependencies.py`: factory simplificada, eliminados `get_llm_client`, `get_odoo_client`, `get_accounting_rules_client`, imports de `LlmClient`, `OdooClient`, `AccountingRulesClient`
- [x] Router `documents.py`: `approve_document` handler ya no usa `await`, eliminados imports de DTOs de asiento

### Fase 9 — Nuevo Use Case: AssignAccountCodesUseCase (llm-service) ✅
- [x] `assign_account_codes.py` — constructor con `ai_service`, `document_client`, `integration_config_client`, `system_prompt_repo`
- [x] `execute(document_id)`: GET full document → GET chart-accounts → GET active prompt → build prompt → call OpenAI → parse → validate detail_id + PUC code → PATCH details → return `{assigned, skipped, warnings}`
- [x] `_parse_response`: extrae JSON del content, valida detail_id y code contra PUC, ignora inválidos con warning
- [x] `integration_config_client.py` (llm-service) — `get_chart_accounts()` best-effort
- [x] `document_client.py` extendido — `get_document_full()` y `patch_detail_codes()`
- [x] `dependencies.py` — factories `get_integration_config_client` y `get_assign_account_codes_use_case`
- [x] System prompt del plan (asignación PUC únicamente) como `_DEFAULT_SYSTEM_PROMPT` en el use case

### Fase 10 — Nuevo HTTP Client: IntegrationConfigClient (llm-service) ✅
Completada como parte de Fase 9.

### Fase 11 — Router accounting.py (llm-service) — Reemplazar endpoints ✅
- [x] Eliminados: `POST /accounting/entries`, `GET /accounting/entries/{document_id}`, `POST /accounting/recalculations`, `POST /accounting/entries/{document_id}/recalculations`
- [x] Creado: `POST /accounting/code-assignments/{document_id}` con Swagger completo
- [x] Mantenidos y actualizados: 3 endpoints de `system-prompts`
- [x] `CodeAssignmentResponse` DTO agregado a `dto/accounting.py`

### Fase 12 — Trigger automático al procesar XML (xml-processor) ✅
- [x] `llm_client.py` reemplazado — `trigger_code_assignment(document_id)` best-effort (timeout 30s)
- [x] `ProcessXmlUseCase` inyecta `llm_client`, llama al final de `execute()` tras RAG
- [x] `dependencies.py` — `get_llm_client` factory + inyección en `get_process_xml_use_case`

### Fase 13 — Limpieza llm-service ✅
- [x] Eliminados: `generate_accounting_entry.py`, `query_accounting.py`, `recalculate_accounting_batch.py`, `recalculate_accounting_document.py`
- [x] Eliminados: `accounting_rules_client.py`, `accounting_entry.py` (model), `accounting_repository.py`
- [x] `main.py` — eliminados `_run_migrations()`, `_migrate_generated_tables()`, import de `accounting_entry` model
- [x] `dependencies.py` — reescrito, solo factories activos (assign, analyze, rag, document, integration_config)
- [x] `system_prompt_repository.py` — `create_default_if_none` apunta a `assign_account_codes._DEFAULT_SYSTEM_PROMPT`

### Fase 14 — Eliminar accounting-rules-service ✅
- [x] `docker-compose.yml` — eliminado bloque completo del servicio + `depends_on` en gateway + `ACCOUNTING_RULES_SERVICE_URL` en xml-processor y llm-service
- [x] `nginx.conf` — eliminadas: variable `$accounting_rules_url`, location `/api/v1/rules`, openapi route, health route
- [x] `.env` — eliminadas 4 variables del bloque accounting-rules-service
- [x] `xml-processor/accounting_rules_client.py` — eliminado en Fase 8

### Fase 15 — DTOs y Swagger ✅
**xml-processor:**
- [x] `DocumentDetailResponse`: agregados `code`, `type`, `tax_id`, `cost_center_id` con Field docs completos
- [x] `DocumentResponse`: reemplazado `accounting_entry_id` → `payment_type_id`
- [x] `DocumentSummaryResponse`: reemplazado `accounting_entry_id` → `payment_type_id`
- [x] Eliminadas clases obsoletas: `AccountingLineResponse`, `AccountingEntryData`, `DocumentDetailWithAccountingResponse`
- [x] Nuevos DTOs: `DocumentDetailCodeUpdateItem`, `DocumentDetailCodeUpdateResponse`
- [x] `GetDocumentDetailWithAccountingUseCase` renombrado → `GetDocumentDetailUseCase`

**llm-service:**
- [x] `CodeAssignmentResponse` agregado
- [x] Eliminadas 9 clases obsoletas: `GenerateAccountingRequest`, `EntryLine`, `EntryLineResponse`, `AccountingEntryResponse`, `DocumentWithAccountingResponse`, `RecalculateAccountingBatchRequest`, `RecalculateAccountingDocumentRequest`, `RecalculateAccountingItemResult`, `RecalculateAccountingBatchResponse`, `RecalculateDocumentBody`
- [x] Import `date` eliminado (ya no usado)

**Documentación:** todos los campos y endpoints nuevos tienen `Field(description=..., examples=[...])` + Swagger completo

### Fase 16 — Tests ✅
**xml-processor (93 passed):**
- [x] Modelos stub creados: `integration_tax.py`, `integration_cost_center.py` (para SQLite in-memory)
- [x] `tests/conftest.py` actualizado — importa los 3 modelos de integration (payment_type, tax, cost_center)
- [x] Tests existentes pasan sin modificación — campos nuevos son nullable, no rompen tests actuales

**llm-service (4 passed):**
- [x] Eliminados: `test_accounting_chart_account_validation.py`, `test_recalculate_accounting_document.py` (testeaban funcionalidad eliminada)
- [x] Tests restantes pasan

### Fase 17 — CLAUDE.md
- [ ] Diagrama de arquitectura: eliminar `accounting-rules-service :8009` y bloque `rules`
- [ ] Tabla endpoints `llm-service`: reemplazar `/accounting/entries/*` por `/accounting/code-assignments/{id}`
- [ ] Tabla endpoints `xml-processor`: actualizar `/documents/{id}/full`
- [ ] Sección "Flujo de datos": reemplazar generación de asiento por asignación de cuentas PUC
- [ ] Sección "Variables de entorno": eliminar `ACCOUNTING_RULES_SERVICE_URL`, cambiar default `DATABASE_NAME` de `xml2data` → `abacus`
- [ ] Sección "Decisiones de diseño": actualizar nota del motor de causación
- [ ] Actualizar `database.py` de todos los servicios: cambiar default `DATABASE_NAME` de `"xml2data"` → `"abacus"`

---

## Archivos Críticos por Servicio

### integration-config-service (`services/integration-config-service/`)
| Archivo | Acción |
|---------|--------|
| `app/infrastructure/persistence/models/cost_center.py` | Eliminar `provider`, `account_key`, cambiar constraint |
| `app/infrastructure/persistence/repositories/cost_center_repository.py` | Eliminar parámetros de provider/account_key |
| `app/application/use_cases/import_cost_centers.py` | Eliminar constantes DEFAULT_PROVIDER/KEY |
| `app/adapters/api/routers/cost_centers.py` | Simplificar llamadas al repositorio |
| `app/adapters/api/routers/internal.py` | Agregar ALTER TABLE migration |

### xml-processor (`services/xml-processor/`)
| Archivo | Acción |
|---------|--------|
| `app/infrastructure/persistence/models/document.py` | Modificar Document + DocumentDetail |
| `app/domain/entities/document.py` | Agregar/eliminar campos |
| `app/application/dto/document.py` | Actualizar DTOs |
| `app/application/use_cases/process_xml.py` | Lógica payment_type_id, tax_id, cost_center_id, trigger LLM |
| `app/application/use_cases/approve_document.py` | Eliminar notificación accounting-rules |
| `app/application/use_cases/get_document_detail.py` | Retornar details con nuevos campos |
| `app/infrastructure/clients/integration_config_client.py` | **NUEVO** |
| `app/infrastructure/clients/accounting_rules_client.py` | **ELIMINAR** |
| `app/adapters/api/routers/documents.py` | Nuevo PATCH /details, actualizar /full |
| `app/adapters/api/routers/internal.py` | Agregar ALTER TABLE migration |

### llm-service (`services/llm-service/`)
| Archivo | Acción |
|---------|--------|
| `app/application/use_cases/assign_account_codes.py` | **NUEVO** |
| `app/application/use_cases/generate_accounting_entry.py` | **ELIMINAR** |
| `app/application/dto/accounting.py` | Reemplazar DTOs |
| `app/adapters/api/routers/accounting.py` | Reemplazar endpoints |
| `app/infrastructure/clients/accounting_rules_client.py` | **ELIMINAR** |
| `app/infrastructure/clients/integration_config_client.py` | **NUEVO** |
| `app/infrastructure/persistence/models/accounting_entry.py` | **ELIMINAR** |
| `app/infrastructure/persistence/repositories/accounting_repository.py` | **ELIMINAR** |
| `app/main.py` | Actualizar registros |

### Infra / todos los servicios
| Archivo | Acción |
|---------|--------|
| `docker-compose.yml` | Eliminar accounting-rules-service |
| `services/gateway/nginx.conf` | Eliminar proxy :8009 |
| `.env` | Eliminar ACCOUNTING_RULES_SERVICE_URL; `DATABASE_NAME=abacus` |
| `services/*/app/infrastructure/config/database.py` | Default `DATABASE_NAME` → `"abacus"` |
| `CLAUDE.md` | Actualizar arquitectura |

---

## Verificación Final

```bash
# 1. Reconstruir servicios afectados
docker-compose up --build xml-processor llm-service integration-config-service

# 2. Provisionar tenant de desarrollo para aplicar migraciones
curl -X POST "http://localhost:8001/internal/provision-tenant?tenant_slug=dev" \
     -H "X-Internal-Secret: ${INTERNAL_SECRET}"
curl -X POST "http://localhost:8007/internal/provision-tenant?tenant_slug=dev" \
     -H "X-Internal-Secret: ${INTERNAL_SECRET}"

# 3. Procesar factura y verificar nuevos campos
# POST /api/v1/documents → GET /api/v1/documents/{id}
# Verificar: payment_type_id en documento, type/code/tax_id/cost_center_id en details

# 4. Disparar asignación de cuentas
# POST /api/v1/accounting/code-assignments/{id}
# Verificar: document_details.code actualizado

# 5. Verificar /full retorna details sin accounting entry
# GET /api/v1/documents/{id}/full

# 6. Correr tests
docker run --rm -v "$(pwd)/services/xml-processor:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"

docker run --rm -v "$(pwd)/services/llm-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"

docker run --rm -v "$(pwd)/services/integration-config-service:/app" --workdir //app python:3.9-slim \
  bash -c "pip install -r requirements.txt -q && python -m pytest tests/ -v"
```
