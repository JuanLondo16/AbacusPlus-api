import asyncio
import json
import logging
import math
import os
from typing import List, Optional

from fastapi import HTTPException, status

from app.application.dto.accounting import GenerateAccountingRequest, AccountingEntryResponse
from app.domain.ports.services import AIServicePort
from app.infrastructure.clients.catalog_client import CatalogClient
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.persistence.models.accounting_entry import AccountingEntry
from app.infrastructure.persistence.repositories.accounting_repository import AccountingRepository
from app.infrastructure.persistence.repositories.chart_account_repository import ChartAccountRepository
from app.infrastructure.persistence.repositories.system_prompt_repository import SystemPromptRepository

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = """\
Eres un experto en contabilidad colombiana (Plan Único de Cuentas - PUC).
Dado el JSON de una factura electrónica DIAN, genera el asiento contable de causación.
Responde ÚNICAMENTE con JSON válido (sin markdown ni texto adicional) con este formato:
{"entries": [{"cuenta": "string", "nombre": "string", "debito": 0.0, "credito": 0.0, "tercero": "string|null", "centro_costo": "string|null", "descripcion": "string|null"}]}

== CAMPOS DEL JSON QUE DEBES USAR ==
- `total`: monto bruto total de la factura (subtotal + IVA).
- `total_taxes`: valor total del IVA de la factura.
- `subtotal`: base gravable sin IVA (campo real, no lo calcules).
- `retefuente`: retención en la fuente (0 si no aplica).
- `reteica`: retención ICA (0 si no aplica).
- `details[].subtotal`: valor SIN IVA de esa línea de detalle.
- `details[].tax_value`: valor del IVA de esa línea de detalle.
- `details[].total`: valor total de esa línea (subtotal + tax_value).
- `details[].concept_account_number`: cuenta PUC asignada a esa línea (puede ser null).
- `details[].description`: descripción del concepto facturado.
- `issuer_tipo_contribuyente`: indica si el emisor es responsable de IVA.
- `issuer_account_number`: cuenta CxP del proveedor (puede ser null).
- `issuer_nit`: NIT del emisor.
- `receiver_nit`: NIT del receptor.

== PASO 1 — CALCULAR VALORES DE CADA LÍNEA ==

A. GASTO O COSTO (débito):
   - Determina la cuenta: usa `concept_account_number` de la línea si existe; si no, busca
     TEXTUALMENTE el término más relevante de `description` dentro de los nombres de la lista
     "CUENTAS PUC CONFIGURADAS". Elige la cuenta cuyo nombre sea semánticamente más cercano.
     NO inventes códigos de cuenta; usa SOLO los de la lista.
   - Calcula el valor de cada línea:
     * Si el emisor ES responsable de IVA: valor_linea = `details[].subtotal` de esa línea.
     * Si el emisor NO es responsable de IVA: valor_linea = `details[].total` de esa línea (IVA absorbido).
   - Si todas las líneas van a la misma cuenta, consolida en una sola entrada.
   - El total de todas las líneas de gasto/costo debe ser:
     * Emisor responsable de IVA  → igual al campo `subtotal` del documento.
     * Emisor NO responsable de IVA → igual al campo `total` del documento (IVA absorbido en el costo).

B. IVA DESCONTABLE (débito) — cuenta 240810:
   - SOLO si `issuer_tipo_contribuyente` indica responsable de IVA Y `total_taxes` > 0.
   - Valor exacto: `total_taxes`.
   - Si el emisor NO es responsable de IVA, NO crees esta línea.
   - Si `total_taxes` == 0, NO crees esta línea aunque el emisor sea responsable de IVA.

C. RETENCIÓN EN LA FUENTE (crédito) — solo si `retefuente` > 0:
   - Cuenta 2365xx según concepto (236515 honorarios, 236540 servicios, 236575 compras).
   - Valor exacto: `retefuente`.
   - tercero: `receiver_nit`.

D. RETENCIÓN ICA (crédito) — solo si `reteica` > 0:
   - Cuenta 236802.
   - Valor exacto: `reteica`.
   - tercero: `receiver_nit`.

E. CUENTAS POR PAGAR — proveedor (crédito):
   - Cuenta: `issuer_account_number` si existe; si no, 220500.
   - Valor exacto: total - retefuente - reteica.
   - tercero: `issuer_nit`. USA SIEMPRE EL NIT, NUNCA EL NOMBRE.

== PASO 2 — VERIFICAR PARTIDA DOBLE ANTES DE RESPONDER ==
Calcula:
  TOTAL_DEBITOS  = suma de todos los campos `debito`
  TOTAL_CREDITOS = suma de todos los campos `credito`

Si TOTAL_DEBITOS ≠ TOTAL_CREDITOS:
  - Identifica la línea de gasto/costo con mayor valor.
  - Ajusta su valor sumando o restando la diferencia exacta hasta que cuadren.
  - NO crees líneas adicionales de ajuste o redondeo.

El asiento final debe cumplir: TOTAL_DEBITOS == TOTAL_CREDITOS == `total`.

== REGLAS ==
- Partida doble obligatoria: sum(debito) == sum(credito). Verifica siempre.
- Cada línea: debito > 0 y credito = 0, O credito > 0 y debito = 0. Nunca ambos > 0.
- Máximo 2 decimales. Usa valores del JSON; los del RAG son solo referencia de cuentas.
- Campo `tercero`: NIT sin puntos ni guiones, nunca el nombre.
- Campo `centro_costo`: asigna según RAG si hay referencia similar; null si no.
"""

_ACCOUNTING_JSON_SCHEMA = {
    "name": "accounting_entry",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["entries"],
        "properties": {
            "entries": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "cuenta",
                        "nombre",
                        "debito",
                        "credito",
                        "tercero",
                        "centro_costo",
                        "descripcion",
                    ],
                    "properties": {
                        "cuenta": {"type": "string", "minLength": 1, "maxLength": 20},
                        "nombre": {"type": "string", "minLength": 1, "maxLength": 200},
                        "debito": {"type": "number", "minimum": 0},
                        "credito": {"type": "number", "minimum": 0},
                        "tercero": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "centro_costo": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "descripcion": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                },
            }
        },
    },
}


async def _safe_fetch(coro, default):
    try:
        return await coro
    except Exception as e:
        logger.warning("Catalog fetch failed: %s", e)
        return default


class GenerateAccountingEntryUseCase:
    def __init__(
        self,
        ai_service: AIServicePort,
        document_client: DocumentClient,
        accounting_repo: AccountingRepository,
        system_prompt_repo: SystemPromptRepository,
        catalog_client: Optional[CatalogClient] = None,
        chart_account_repo: Optional[ChartAccountRepository] = None,
    ):
        self._ai = ai_service
        self._doc_client = document_client
        self._catalog_client = catalog_client
        self._accounting_repo = accounting_repo
        self._prompt_repo = system_prompt_repo
        self._chart_account_repo = chart_account_repo
        self._chart_account_provider = os.getenv("INTEGRATION_CHART_ACCOUNT_PROVIDER", "siigo").strip().lower()
        self._chart_account_key = os.getenv("INTEGRATION_CHART_ACCOUNT_KEY", "default").strip()
        self._adj_account = os.getenv("ACCOUNTING_ADJUSTMENT_ACCOUNT", "539520")
        self._adj_name = os.getenv("ACCOUNTING_ADJUSTMENT_ACCOUNT_NAME", "Ajuste por redondeo")
        self._fallback_accounts = [
            ("2365", os.getenv("FALLBACK_RETEFUENTE_ACCOUNT", "23659501")),
            ("2368", os.getenv("FALLBACK_RETEICA_ACCOUNT", "23689501")),
            ("236",  os.getenv("FALLBACK_RETENCION_ACCOUNT", "23659501")),
            ("22",   os.getenv("FALLBACK_CXP_ACCOUNT", "22050501")),
            ("5",    os.getenv("FALLBACK_GASTO_ACCOUNT", "51999999")),
            ("6",    os.getenv("FALLBACK_COSTO_ACCOUNT", "61999999")),
        ]

    async def execute(self, request: GenerateAccountingRequest) -> AccountingEntryResponse:
        # 1. Obtener documento
        document = await self._doc_client.get_document(request.document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Documento {request.document_id} no encontrado en xml-processor.",
            )

        # 2. P2: Enriquecer documento con datos contables del emisor
        issuer_nit = document.get("issuer_nit", "")
        if issuer_nit:
            try:
                issuer_data = await self._doc_client.get_issuer(issuer_nit)
                if issuer_data:
                    document = dict(document)
                    document["issuer_account_number"] = issuer_data.get("account_number") or None
                    document["issuer_tipo_contribuyente"] = issuer_data.get("tipo_contribuyente") or None
                    document["issuer_notes"] = issuer_data.get("notes") or None
                    logger.info(
                        "Emisor enriquecido: NIT=%s cuenta=%s tipo=%s notes=%s",
                        issuer_nit,
                        document["issuer_account_number"],
                        document["issuer_tipo_contribuyente"],
                        document["issuer_notes"],
                    )
            except Exception as e:
                logger.warning("No se pudo enriquecer emisor NIT=%s: %s", issuer_nit, e)

        # 3. P3: Obtener catálogo contable (centros de costo, PUC, retenciones) — best-effort
        cost_centers: List[dict] = []
        puc_accounts: List[dict] = []
        retefuente_rates: List[dict] = []
        if self._catalog_client:
            cost_centers, puc_accounts, retefuente_rates = await asyncio.gather(
                _safe_fetch(self._catalog_client.get_cost_centers(), []),
                _safe_fetch(self._catalog_client.get_puc_accounts(), []),
                _safe_fetch(self._catalog_client.get_retention_fuente_rates(), []),
            )
            logger.info(
                "Catálogo: %d CC | %d PUC | %d reteFuente",
                len(cost_centers), len(puc_accounts), len(retefuente_rates),
            )

        chart_accounts = self._get_registered_chart_accounts()
        if chart_accounts:
            puc_accounts = chart_accounts
            logger.info(
                "Plan de cuentas validado desde integration_chart_accounts: %d cuentas provider=%s account_key=%s",
                len(chart_accounts),
                self._chart_account_provider,
                self._chart_account_key,
            )

        # 4. Obtener system prompt activo
        active_prompt = self._prompt_repo.get_active()
        system_prompt_text = active_prompt.content if active_prompt else _DEFAULT_SYSTEM_PROMPT
        system_prompt_id = active_prompt.id if active_prompt else None

        # 5. Buscar asientos históricos similares en la base de datos (últimos 12 meses, mismo NIT).
        # Se recuperan hasta 50 candidatos y se rankean por similitud textual de descripciones.
        historical_candidates = self._accounting_repo.find_historical_by_issuer(
            issuer_nit=issuer_nit,
            months_back=12,
            limit=50,
        )
        logger.info(
            "Histórico DB: %d candidatos para NIT=%s doc_id=%d",
            len(historical_candidates), issuer_nit, request.document_id,
        )

        current_descriptions = " ".join(
            d.get("description", "") for d in document.get("details", [])
        )
        if historical_candidates and current_descriptions.strip():
            historical_candidates = sorted(
                historical_candidates,
                key=lambda e: self._word_overlap(
                    current_descriptions,
                    " ".join(l.get("descripcion", "") or "" for l in e["lines"]),
                ),
                reverse=True,
            )

        historical_entries = historical_candidates[:request.top_k]

        if not historical_entries:
            logger.info(
                "Sin históricos en DB para NIT=%s; el LLM usará solo system prompt, catálogo y JSON.",
                issuer_nit,
            )

        # 6. Construir prompt de usuario
        doc_json = json.dumps(document, ensure_ascii=False, default=str, indent=2)

        historical_prompt = ""
        if historical_entries:
            hist_refs = "\n\n".join(
                f"[Asiento histórico {i+1} — {e['created_at'][:10]}]\n"
                + "\n".join(
                    f"  Cuenta: {l['cuenta']} {l['nombre']}"
                    + (f" | CC: {l['centro_costo']}" if l.get("centro_costo") else "")
                    + (f" | Desc: {l['descripcion']}" if l.get("descripcion") else "")
                    for l in e["lines"]
                )
                for i, e in enumerate(historical_entries)
            )
            historical_prompt = (
                "ASIENTOS HISTÓRICOS DE REFERENCIA (base de datos interna)\n"
                "(usa SOLO para inferir la distribución de cuentas PUC y centros de costo —\n"
                " NO copies valores monetarios; tómalos exclusivamente del JSON de la factura.\n"
                " Si los históricos muestran distribuciones distintas para la misma naturaleza\n"
                " de gasto, elige la distribución más apropiada al contexto de esta factura):\n"
                f"{hist_refs}\n\n"
            )

        catalog_prompt = self._build_catalog_prompt(cost_centers, puc_accounts, retefuente_rates)

        issuer_notes = document.get("issuer_notes")
        issuer_notes_block = (
            f"== REGLA ESPECIFICA PARA ESTE PROVEEDOR — PRIORIDAD MAXIMA ==\n"
            f"{issuer_notes}\n"
            f"Esta instruccion tiene PRIORIDAD sobre el catalogo de cuentas y sobre el historico. "
            f"Aplica LITERALMENTE al determinar la cuenta de gasto/costo.\n\n"
        ) if issuer_notes else ""

        user_prompt = (
            f"{catalog_prompt}"
            f"{issuer_notes_block}"
            f"{historical_prompt}"
            f"FACTURA A CAUSAR (JSON):\n{doc_json}\n\n"
            f"Genera el asiento contable de causación para la factura anterior. "
            f"Usa los valores monetarios del JSON de la factura, no los de las referencias. "
            f"Devuelve únicamente JSON válido con la clave 'entries'."
        )

        # Snapshot de los históricos usados como referencia (para auditoría)
        historical_context_snapshot = [
            {
                "source_type": "db_historical_entry",
                "source_id": e["entry_id"],
                "created_at": e["created_at"],
                "lines": e["lines"],
            }
            for e in historical_entries
        ]

        # 7. Llamar al LLM
        try:
            result = await self._ai.complete(
                prompt=user_prompt,
                model=request.model,
                system_prompt=system_prompt_text,
                temperature=0.1,
                json_schema=_ACCOUNTING_JSON_SCHEMA,
            )
            raw_response = result["content"]

            # 8. Parsear JSON de la respuesta
            parsed = self._parse_entries(raw_response)
            parsed = self._normalize_entries(parsed)
            logger.debug(
                "LLM entries before validation doc_id=%d: %s",
                request.document_id,
                json.dumps(parsed, ensure_ascii=False),
            )
            parsed = self._validate_cxp_side(parsed)
            parsed = self._validate_cxp_exists(parsed)
            parsed = self._correct_cxp_value(parsed, document)
            parsed = self._strip_zero_iva_lines(parsed, document)
            parsed = self._validate_gasto_vs_subtotal(parsed, document)
            parsed = self._validate_tax_entries(parsed, document)
            parsed = self._validate_and_repair_entries(parsed)
            parsed = self._validate_registered_accounts(parsed, chart_accounts)

            entry = AccountingEntry(
                document_id=request.document_id,
                issuer_nit=issuer_nit or None,
                issuer_name=document.get("issuer_name") or None,
                system_prompt_id=system_prompt_id,
                model_used=request.model,
                status="generated",
                rag_context=historical_context_snapshot,
            )
            saved = self._accounting_repo.create(entry, lines_data=parsed)
            self._accounting_repo.link_to_document(request.document_id, saved.id)
        except Exception as e:
            logger.error("Error generando causación para doc_id=%d: %s", request.document_id, e)
            entry = AccountingEntry(
                document_id=request.document_id,
                issuer_nit=issuer_nit or None,
                issuer_name=document.get("issuer_name") or None,
                system_prompt_id=system_prompt_id,
                model_used=request.model,
                status="error",
                error_message=str(e),
                rag_context=historical_context_snapshot,
            )
            saved = self._accounting_repo.create(entry, lines_data=[])

        return AccountingEntryResponse.model_validate(saved)

    def _build_catalog_prompt(
        self,
        cost_centers: List[dict],
        puc_accounts: List[dict],
        retefuente_rates: List[dict],
    ) -> str:
        parts = []

        if cost_centers:
            cc_lines = "\n".join(f"  {cc['code']} — {cc['name']}" for cc in cost_centers)
            parts.append(
                "== CENTROS DE COSTO DISPONIBLES ==\n"
                "Asigna el más apropiado según el tipo de gasto (o null si no corresponde):\n"
                f"{cc_lines}"
            )

        if puc_accounts:
            puc_lines = "\n".join(f"  {a['code']} — {a['name']}" for a in puc_accounts)
            parts.append(
                "== CUENTAS PUC CONFIGURADAS PARA ESTA EMPRESA ==\n"
                "Usa UNICAMENTE estas cuentas; la causación será rechazada si incluye "
                "cuentas no registradas o inactivas en el sistema:\n"
                f"{puc_lines}"
            )

            # Identificar cuenta CxP por defecto para proveedores nacionales
            cxp_accounts = [a for a in puc_accounts if str(a.get("code", "")).startswith("22")]
            nacional_cxp = next(
                (a for a in cxp_accounts if "nacional" in (a.get("name") or "").lower()),
                cxp_accounts[0] if cxp_accounts else None,
            )
            if nacional_cxp:
                parts.append(
                    "== CUENTA CxP POR DEFECTO ==\n"
                    "Cuando el proveedor NO tiene cuenta CxP asignada en `issuer_account_number`, "
                    f"usa OBLIGATORIAMENTE: {nacional_cxp['code']} — {nacional_cxp['name']}. "
                    "NO uses 220500 ni ninguna otra cuenta que no esté en el plan configurado."
                )
        else:
            parts.append(
                "== CUENTAS PUC ==\n"
                "No hay plan de cuentas configurado para esta empresa. "
                "Usa tu criterio de experto en contabilidad colombiana (PUC) "
                "para asignar las cuentas más apropiadas según la naturaleza del gasto."
            )

        if retefuente_rates:
            rate_lines = "\n".join(
                f"  Concepto: {r.get('retention_concept', '')} | Contribuyente: {r.get('taxpayer_type', '')} | Tarifa: {r.get('rate_percentage', '')}%"
                + (f" | Base UVT: {r['minimum_base_uvt']}" if r.get("minimum_base_uvt") is not None else "")
                + (f" | Base Pesos: {r['minimum_base_pesos']}" if r.get("minimum_base_pesos") is not None else "")
                for r in retefuente_rates
            )
            parts.append(
                "== TASAS DE RETENCIÓN EN LA FUENTE ==\n"
                "(referencia para elegir la subcuenta 2365xx correcta según concepto, tipo de proveedor y comparar las bases mínimas)\n"
                f"{rate_lines}"
            )

        return "\n\n".join(parts) + "\n\n" if parts else ""

    @staticmethod
    def _word_overlap(text_a: str, text_b: str) -> float:
        """Similitud de Jaccard sobre tokens para rankear históricos por naturaleza del gasto."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    def _parse_entries(self, raw: str) -> list:
        """Extrae el JSON de la respuesta del LLM, tolerando texto extra."""
        text = raw.strip()
        # Buscar el primer { y el último }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"La respuesta del LLM no contiene JSON válido: {text[:200]}")
        data = json.loads(text[start:end])
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("La respuesta del LLM no contiene una lista válida en 'entries'.")
        return entries

    def _normalize_entries(self, entries: list) -> list[dict]:
        normalized: list[dict] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            cuenta = str(e.get("cuenta") or "").strip()
            nombre = str(e.get("nombre") or "").strip()
            if not cuenta or not nombre:
                continue
            debito = self._to_money(e.get("debito"))
            credito = self._to_money(e.get("credito"))
            tercero = e.get("tercero")
            centro_costo = e.get("centro_costo")
            descripcion = e.get("descripcion")

            normalized.append(
                {
                    "cuenta": cuenta,
                    "nombre": nombre,
                    "debito": debito,
                    "credito": credito,
                    "tercero": str(tercero).strip() if isinstance(tercero, str) and tercero.strip() else None,
                    "centro_costo": str(centro_costo).strip() if isinstance(centro_costo, str) and centro_costo.strip() else None,
                    "descripcion": str(descripcion).strip() if isinstance(descripcion, str) and descripcion.strip() else None,
                }
            )
        return normalized

    def _correct_cxp_value(self, entries: list[dict], document: dict) -> list[dict]:
        """Corrige el valor de la línea CxP cuando el LLM olvidó restar las retenciones.
        CxP esperado = total - retefuente - reteica."""
        total = float(document.get("total") or 0)
        retefuente = float(document.get("retefuente") or 0)
        reteica = float(document.get("reteica") or 0)
        expected_cxp = self._to_money(total - retefuente - reteica)

        cxp_lines = [
            e for e in entries
            if str(e.get("cuenta", "")).startswith("22") and float(e.get("credito") or 0) > 0
        ]
        if not cxp_lines:
            return entries

        actual_cxp = self._to_money(sum(float(e["credito"]) for e in cxp_lines))
        if math.isclose(actual_cxp, expected_cxp, abs_tol=0.01):
            return entries

        logger.warning(
            "CxP incorrecto: LLM generó credito=%.2f pero expected=%.2f (retenciones no restadas). Corrigiendo.",
            actual_cxp, expected_cxp,
        )

        factor = expected_cxp / actual_cxp
        accumulated = 0.0
        for i, e in enumerate(cxp_lines):
            if i < len(cxp_lines) - 1:
                new_val = self._to_money(float(e["credito"]) * factor)
                e["credito"] = new_val
                accumulated += new_val
            else:
                e["credito"] = self._to_money(expected_cxp - accumulated)

        return entries

    def _validate_cxp_side(self, entries: list[dict]) -> list[dict]:
        """
        Las cuentas CxP (220xxx / 221xxx) siempre van al crédito.
        Si el LLM las colocó en débito, se corrigen automáticamente.
        """
        for e in entries:
            cuenta = str(e.get("cuenta", ""))
            if (
                cuenta[:3] in ("220", "221")
                and float(e.get("debito") or 0) > 0
                and float(e.get("credito") or 0) == 0
            ):
                logger.warning(
                    "CxP cuenta %s generada en débito — corrigiendo a crédito automáticamente.", cuenta
                )
                e["credito"] = e["debito"]
                e["debito"] = 0.0
        return entries

    def _validate_cxp_exists(self, entries: list[dict]) -> list[dict]:
        """Verifica que exista al menos una línea de CxP (22xxxx) en el crédito."""
        has_cxp = any(
            str(e.get("cuenta", "")).startswith("22") and float(e.get("credito") or 0) > 0
            for e in entries
        )
        if not has_cxp:
            raise ValueError(
                "El asiento no contiene una línea de cuentas por pagar (22xxxx) en el crédito "
                "con el valor neto a pagar al proveedor."
            )
        return entries

    def _validate_tax_entries(self, entries: list[dict], document: dict) -> list[dict]:
        """Verifica que existan líneas de retención cuando retefuente/reteica > 0."""
        retefuente = float(document.get("retefuente") or 0)
        reteica = float(document.get("reteica") or 0)

        if retefuente > 0:
            has_retefuente = any(
                str(e.get("cuenta", "")).startswith("2365") and float(e.get("credito") or 0) > 0
                for e in entries
            )
            if not has_retefuente:
                raise ValueError(
                    f"El documento tiene retefuente={retefuente:.2f} pero no hay línea de "
                    "retención en la fuente (2365xx) en el crédito."
                )

        if reteica > 0:
            has_reteica = any(
                str(e.get("cuenta", "")).startswith("2368") and float(e.get("credito") or 0) > 0
                for e in entries
            )
            if not has_reteica:
                raise ValueError(
                    f"El documento tiene reteica={reteica:.2f} pero no hay línea de "
                    "retención ICA (2368xx) en el crédito."
                )

        return entries

    def _strip_zero_iva_lines(self, entries: list[dict], document: dict) -> list[dict]:
        """Elimina líneas 2408xx en débito cuando total_taxes == 0 para prevenir alucinaciones del LLM."""
        total_taxes = float(document.get("total_taxes") or 0)
        if total_taxes > 0:
            return entries
        cleaned = [
            e for e in entries
            if not (str(e.get("cuenta", "")).startswith("2408") and float(e.get("debito") or 0) > 0)
        ]
        if len(cleaned) < len(entries):
            logger.warning(
                "Se eliminaron %d línea(s) 2408xx con total_taxes=0 (alucinación del LLM).",
                len(entries) - len(cleaned),
            )
        return cleaned

    def _validate_gasto_vs_subtotal(self, entries: list[dict], document: dict) -> list[dict]:
        """
        Valida y corrige la suma de las líneas de gasto/costo:
        - Con IVA (línea 2408xx en débito): gasto debe == total - total_taxes.
          Se usa esta fórmula (no el campo subtotal) porque el XML de DIAN puede
          traer subtotal inconsistente con total y total_taxes.
        - Sin IVA: gasto debe == total.
        Si el LLM distribuyó mal los montos, redistribuye proporcionalmente.
        Cuentas de control: 2408xx (IVA), 2xxxxx (pasivos/CxP/retenciones).
        """
        _IVA_PREFIX = "2408"
        _PASIVO_PREFIXES = ("2",)

        has_iva_debit = any(
            str(e.get("cuenta", "")).startswith(_IVA_PREFIX) and float(e.get("debito") or 0) > 0
            for e in entries
        )

        # Con IVA → target es total - total_taxes (evita usar subtotal que puede ser inconsistente en el XML)
        # Sin IVA → target es total
        total = float(document.get("total") or 0)
        total_taxes = float(document.get("total_taxes") or 0)
        target = self._to_money(total - total_taxes) if has_iva_debit else total
        if not target:
            return entries

        def is_gasto(e: dict) -> bool:
            cuenta = str(e.get("cuenta", ""))
            debito = float(e.get("debito") or 0)
            return debito > 0 and not cuenta.startswith(_IVA_PREFIX) and not cuenta.startswith(_PASIVO_PREFIXES)

        gasto_entries = [e for e in entries if is_gasto(e)]
        if not gasto_entries:
            return entries

        sum_gasto = sum(float(e["debito"]) for e in gasto_entries)
        if math.isclose(sum_gasto, target, abs_tol=0.01):
            return entries

        logger.warning(
            "Gasto incorrecto: LLM generó sum_gasto=%.2f pero target=%.2f (has_iva=%s). "
            "Redistribuyendo proporcionalmente.",
            sum_gasto, target, has_iva_debit,
        )

        # Redistribuir proporcionalmente al target
        factor = target / sum_gasto
        accumulated = 0.0
        for i, e in enumerate(gasto_entries):
            if i < len(gasto_entries) - 1:
                new_val = self._to_money(float(e["debito"]) * factor)
                e["debito"] = new_val
                accumulated += new_val
            else:
                # Última línea absorbe el residuo para garantizar suma exacta
                e["debito"] = self._to_money(target - accumulated)

        return entries

    def _validate_and_repair_entries(self, entries: list[dict]) -> list[dict]:
        if len(entries) < 2:
            raise ValueError("El asiento debe contener al menos 2 líneas.")

        repaired: list[dict] = []
        for e in entries:
            d = float(e.get("debito") or 0)
            c = float(e.get("credito") or 0)
            if d < 0 or c < 0:
                raise ValueError("Los montos no pueden ser negativos.")
            if d > 0 and c > 0:
                # regla estricta: dividir en dos líneas no es seguro; mejor fallar
                raise ValueError("Una línea no puede tener débito y crédito simultáneamente.")
            if d == 0 and c == 0:
                continue
            repaired.append(e)

        if len(repaired) < 2:
            raise ValueError("El asiento debe contener al menos 2 líneas con valor.")

        sum_deb = self._to_money(sum(float(e["debito"]) for e in repaired))
        sum_cre = self._to_money(sum(float(e["credito"]) for e in repaired))
        diff = self._to_money(sum_deb - sum_cre)

        # Tolerancia por redondeos: 1 centavo
        if math.isclose(diff, 0.0, abs_tol=0.01):
            return repaired

        if abs(diff) > 0.03:
            raise ValueError(
                f"El asiento no cuadra y la diferencia ({abs(diff):.2f} pesos) supera el máximo "
                "de ajuste permitido (0.03 pesos). Revise los valores del asiento."
            )

        adj_line = {
            "cuenta": self._adj_account,
            "nombre": self._adj_name,
            "debito": 0.0,
            "credito": 0.0,
            "tercero": None,
            "centro_costo": None,
            "descripcion": "Ajuste por redondeo (autogenerado)",
        }
        if diff > 0:
            # hay más débito que crédito, falta crédito
            adj_line["credito"] = abs(diff)
        else:
            adj_line["debito"] = abs(diff)
        repaired.append(adj_line)

        # Revalidar
        sum_deb2 = self._to_money(sum(float(e["debito"]) for e in repaired))
        sum_cre2 = self._to_money(sum(float(e["credito"]) for e in repaired))
        if not math.isclose(sum_deb2, sum_cre2, abs_tol=0.01):
            raise ValueError("No fue posible balancear el asiento contable.")
        return repaired

    def _to_money(self, value) -> float:
        try:
            v = float(value)
        except Exception:
            v = 0.0
        # Normalizar a 2 decimales
        return round(v + 1e-12, 2)

    def _get_registered_chart_accounts(self) -> list[dict]:
        if not self._chart_account_repo:
            return []
        try:
            return self._chart_account_repo.list_active(
                provider=self._chart_account_provider,
                account_key=self._chart_account_key,
            )
        except Exception as e:
            raise ValueError(
                "No fue posible consultar integration_chart_accounts para validar el plan de cuentas."
            ) from e

    def _validate_registered_accounts(self, entries: list[dict], chart_accounts: list[dict]) -> list[dict]:
        if not chart_accounts:
            return entries

        account_map = {str(a["code"]).strip(): a for a in chart_accounts}

        # Las líneas de ajuste por redondeo las genera el sistema, no el LLM;
        # no deben fallar validación aunque la cuenta no esté en el plan configurado.
        llm_entries = [e for e in entries if e.get("descripcion") != "Ajuste por redondeo (autogenerado)"]

        missing_uncorrected: list[str] = []
        for entry in llm_entries:
            code = str(entry.get("cuenta") or "").strip()
            if code in account_map:
                entry["nombre"] = account_map[code].get("name") or entry["nombre"]
                continue

            # Buscar fallback por categoría
            fallback_code = None
            for prefix, fb in self._fallback_accounts:
                if code.startswith(prefix) and fb in account_map:
                    fallback_code = fb
                    break

            if fallback_code:
                logger.warning(
                    "Cuenta %s no registrada → sustituyendo por fallback %s (%s).",
                    code, fallback_code, account_map[fallback_code].get("name"),
                )
                entry["cuenta"] = fallback_code
                entry["nombre"] = account_map[fallback_code].get("name") or entry["nombre"]
            else:
                missing_uncorrected.append(code)

        if missing_uncorrected:
            raise ValueError(
                "La causación contiene cuentas no registradas o inactivas en "
                "integration_chart_accounts: "
                + ", ".join(sorted(set(missing_uncorrected)))
            )

        return entries
