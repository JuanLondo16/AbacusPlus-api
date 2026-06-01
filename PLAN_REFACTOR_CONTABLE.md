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

### Fase 4 — HTTP Client: IntegrationConfigClient (xml-processor)
**Nuevo archivo:** `services/xml-processor/app/infrastructure/clients/integration_config_client.py`
- [ ] Método `async get_taxes() -> list[dict]` → `GET /api/v1/integrations/taxes?active=true`
- [ ] Timeout 5s, best-effort (retorna `[]` en fallo)
- [ ] Registrar en `dependencies.py`

### Fase 5 — Lógica de Enriquecimiento en process_xml.py
**Archivo:** `services/xml-processor/app/application/use_cases/process_xml.py`

**payment_type_id:**
- [ ] Leer `issuer.payment_id` y asignarlo a `document.payment_type_id` antes de persistir

**tax_id (por cada detail):**
- [ ] Fetch taxes de integration-config-service una vez por invocación del use case
- [ ] Función `_match_tax(tax_type_str, taxes)`:
  - [ ] Match `name` case-insensitive contra `tax_type_str`
  - [ ] Si falla, parsear `tax_type_str` como float y comparar con `tax.percentage`
- [ ] Si `tax_type in ("0", "", "0.00")` → `tax_id = None` sin búsqueda
- [ ] Si no hay match → `tax_id = None` + `logger.warning(...)`

**cost_center_id (por cada detail):**
- [ ] Método `find_cost_center_by_similar_description(issuer_id, description)` en repositorio
  - [ ] SQL con `similarity()` (pg_trgm) o `ILIKE` con tokens clave
  - [ ] Filtro: `document.issuer_id = issuer_id AND detail.cost_center_id IS NOT NULL`
- [ ] Tomar `most_common(1)` del resultado
- [ ] Sin resultado → `cost_center_id = None`

### Fase 6 — Nuevo Endpoint PATCH /documents/{id}/details (xml-processor)
**Archivo:** `services/xml-processor/app/adapters/api/routers/documents.py`
- [ ] `PATCH /api/v1/documents/{document_id}/details`
- [ ] Body: `list[{detail_id: int, code: str, type: str}]`
- [ ] Use case / repositorio: bulk UPDATE `document_details`
- [ ] Status 200, respuesta `{updated: int}`
- [ ] Documentación Swagger completa

### Fase 7 — Actualizar GET /documents/{id}/full (xml-processor)
**Archivo:** `services/xml-processor/app/application/use_cases/get_document_detail.py`
- [ ] Eliminar fetch de accounting entry (OdooClient, LlmClient)
- [ ] Retornar `document + details` completos (con `code`, `type`, `tax_id`, `cost_center_id`)
- [ ] Actualizar DTO `DocumentFullResponse` (antes `DocumentDetailWithAccountingResponse`)
- [ ] Eliminar dependencias de `OdooClient` y `LlmClient` del use case

### Fase 8 — Limpieza approve_document.py (xml-processor)
**Archivo:** `services/xml-processor/app/application/use_cases/approve_document.py`
- [ ] Eliminar `_notify_rules_service()` método completo
- [ ] Eliminar `accounting_rules_client` del constructor
- [ ] Eliminar import de `AccountingRulesClient`

### Fase 9 — Nuevo Use Case: AssignAccountCodesUseCase (llm-service)
**Nuevo archivo:** `services/llm-service/app/application/use_cases/assign_account_codes.py`
- [ ] Constructor: `document_client`, `integration_config_client`, `ai_service`, `system_prompt_repo`
- [ ] `execute(document_id)`:
  - [ ] GET document con details desde xml-processor
  - [ ] GET chart-accounts desde integration-config-service (filtrar `accepts_movements=True`)
  - [ ] GET historical assignments — details con `code IS NOT NULL` del mismo emisor
  - [ ] GET active system prompt
  - [ ] Construir user_prompt (items, PUC, historial, notas issuer)
  - [ ] Llamar OpenAI
  - [ ] Parsear JSON respuesta
  - [ ] Validar `detail_id` existe y `code` existe en PUC
  - [ ] PATCH `/api/v1/documents/{id}/details` con assignments válidos
  - [ ] Retornar `{assigned, skipped, warnings}`

**Sistema prompt:**
- [ ] Usar el prompt de la Fase 4.3 del enunciado (asignación de cuentas PUC únicamente)
- [ ] Crear en `system_prompts` table al iniciar (o vía `POST /accounting/system-prompts`)

### Fase 10 — Nuevo HTTP Client: IntegrationConfigClient (llm-service)
**Nuevo archivo:** `services/llm-service/app/infrastructure/clients/integration_config_client.py`
- [ ] Método `async get_chart_accounts(active_only=True) -> list[dict]` → `GET /api/v1/integrations/chart-accounts`
- [ ] Timeout 5s, best-effort

### Fase 11 — Router accounting.py (llm-service) — Reemplazar endpoints
**Archivo:** `services/llm-service/app/adapters/api/routers/accounting.py`
- [ ] Eliminar `POST /accounting/entries`
- [ ] Eliminar `GET /accounting/entries/{document_id}`
- [ ] Eliminar `POST /accounting/recalculations`
- [ ] Eliminar `POST /accounting/entries/{document_id}/recalculations`
- [ ] Crear `POST /accounting/code-assignments/{document_id}`
  - [ ] Llama `AssignAccountCodesUseCase.execute(document_id)`
  - [ ] Status 200, best-effort
  - [ ] Documentación Swagger completa
- [ ] Mantener y actualizar descripción de endpoints `system-prompts`

### Fase 12 — Trigger automático al procesar XML (xml-processor)
**Archivo:** `services/xml-processor/app/application/use_cases/process_xml.py`
- [ ] Al final de `execute()`, llamada best-effort a `POST /api/v1/accounting/code-assignments/{document_id}` vía `LlmClient`
- [ ] Patrón idéntico al de indexación RAG existente: fallo no bloquea, solo loguea warning

### Fase 13 — Limpieza llm-service
- [ ] Eliminar `app/application/use_cases/generate_accounting_entry.py`
- [ ] Eliminar `app/infrastructure/clients/accounting_rules_client.py`
- [ ] Eliminar `app/infrastructure/persistence/models/accounting_entry.py`
- [ ] Eliminar `app/infrastructure/persistence/repositories/accounting_repository.py`
- [ ] Actualizar `app/main.py` — quitar imports y registros de lo eliminado

### Fase 14 — Eliminar accounting-rules-service
- [ ] `docker-compose.yml` — eliminar servicio `accounting-rules-service`
- [ ] `services/gateway/nginx.conf` — eliminar location block para `:8009`
- [ ] `.env` — eliminar `ACCOUNTING_RULES_SERVICE_URL`
- [ ] `xml-processor`: eliminar `accounting_rules_client.py` de `infrastructure/clients/`
- [ ] Confirmar si se desea snapshot de tabla `accounting_rules` antes de eliminar el servicio

### Fase 15 — DTOs y Swagger
**xml-processor:**
- [ ] `DocumentResponse`: eliminar `accounting_entry_id`, agregar `payment_type_id`
- [ ] `DocumentDetailResponse`: agregar `code`, `type`, `tax_id`, `cost_center_id`
- [ ] `DocumentSummaryResponse`: eliminar `accounting_entry_id`, agregar `payment_type_id`
- [ ] Renombrar `DocumentDetailWithAccountingResponse` → `DocumentFullResponse` con campo `details`
- [ ] Nuevo `DocumentDetailCodeUpdateRequest` para el PATCH bulk

**llm-service:**
- [ ] Nuevo `CodeAssignmentResponse {assigned: int, skipped: int, warnings: list[str]}`
- [ ] Eliminar `GenerateAccountingRequest`, `AccountingEntryResponse`, `EntryLineResponse`

**Documentación:**
- [ ] Todos los campos nuevos con `Field(description=..., examples=[...])`
- [ ] Todos los endpoints nuevos/modificados con `summary`, `description`, `response_description`, códigos de error

### Fase 16 — Tests
**xml-processor:**
- [ ] `test_payment_type_assignment`: issuer con `payment_id` → documento hereda `payment_type_id`
- [ ] `test_tax_id_match_by_name`: `tax_type="IVA"` matchea por nombre
- [ ] `test_tax_id_match_by_percentage`: `tax_type="19.00"` matchea por percentage
- [ ] `test_tax_id_no_match_logs_warning`: sin match → `tax_id=None` + warning
- [ ] `test_tax_id_zero_skipped`: `tax_type="0"` → `tax_id=None` sin búsqueda
- [ ] `test_cost_center_historical_match`: historial disponible → toma más frecuente
- [ ] `test_cost_center_no_history`: sin historial → `cost_center_id=None`
- [ ] Actualizar tests existentes que fallen por `accounting_entry_id` eliminado

**llm-service:**
- [ ] `test_assign_codes_happy_path`: LLM retorna JSON válido → details actualizados
- [ ] `test_assign_codes_invalid_puc_code`: código no existe en PUC → warning, no actualiza
- [ ] `test_assign_codes_invalid_detail_id`: detail_id desconocido → warning, skip
- [ ] Actualizar/eliminar tests de `generate_accounting_entry`

**integration-config-service:**
- [ ] `test_upsert_cost_centers_no_provider`: import sin `provider`/`account_key` funciona
- [ ] `test_list_cost_centers_no_provider`: list sin filtros retorna todos los activos

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
