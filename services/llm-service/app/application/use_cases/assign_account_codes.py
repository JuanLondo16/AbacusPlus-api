import json
import logging

from app.domain.ports.services import AIServicePort
from app.infrastructure.clients.document_client import DocumentClient
from app.infrastructure.clients.integration_config_client import IntegrationConfigClient
from app.infrastructure.persistence.repositories.system_prompt_repository import (
    SystemPromptRepository,
)

logger = logging.getLogger(__name__)

# La instrucción "solo JSON" se repite dos veces en el prompt: los LLMs respetan
# mejor las restricciones de formato cuando se refuerzan explícitamente.
_DEFAULT_SYSTEM_PROMPT = """\
Eres un experto en contabilidad colombiana especializado en la asignación de cuentas del \
Plan Único de Cuentas (PUC) para facturas de compra electrónicas DIAN.

Tu única tarea es asignar la cuenta contable correcta del PUC a cada ítem de una factura, \
basándote en:
1. La descripción y naturaleza del ítem
2. El plan de cuentas disponible (PUC)
3. El historial de asignaciones previas para el mismo proveedor e ítems similares
4. Las notas específicas del proveedor, si aplican

REGLAS ESTRICTAS:
- Responde ÚNICAMENTE con un objeto JSON. Sin explicaciones, sin markdown, sin texto adicional.
- Responde ÚNICAMENTE con un objeto JSON. Sin explicaciones, sin markdown, sin texto adicional.
- El JSON debe tener exactamente esta estructura:
  {
    "items": [
      {
        "item_id": "<id exacto recibido>",
        "description": "<descripción del ítem>",
        "suggested_account_code": "<código PUC>",
        "suggested_account_name": "<nombre de la cuenta PUC>"
      }
    ]
  }
- El campo "item_id" debe ser exactamente el mismo valor recibido en el input, sin modificación.
- El campo "suggested_account_code" debe ser un código existente en el PUC proporcionado.
- NO calcules valores monetarios.
- NO valides débitos ni créditos.
- NO generes asientos contables.
- NO agregues campos adicionales al JSON.
- Si no puedes determinar la cuenta con certeza razonable, asigna la cuenta de gastos generales más apropiada \
  según el PUC.\
"""


class AssignAccountCodesUseCase:
    """Asigna cuentas PUC a cada línea de detalle de un documento usando el LLM."""

    def __init__(
        self,
        ai_service: AIServicePort,
        document_client: DocumentClient,
        integration_config_client: IntegrationConfigClient,
        system_prompt_repo: SystemPromptRepository,
    ):
        self._ai = ai_service
        self._document_client = document_client
        self._integration_config_client = integration_config_client
        self._system_prompt_repo = system_prompt_repo

    async def execute(self, document_id: int) -> dict:
        """Asigna cuentas PUC a las líneas del documento y las persiste vía xml-processor.

        Retorna {assigned, skipped, warnings}.
        """
        warnings: list[str] = []

        document = await self._document_client.get_document_full(document_id)
        if document is None:
            raise ValueError(f"Documento {document_id} no encontrado en xml-processor")

        details = document.get("details", [])
        if not details:
            return {"assigned": 0, "skipped": 0, "warnings": ["Documento sin líneas de detalle"]}

        chart_accounts = await self._integration_config_client.get_chart_accounts()
        puc_index = {acc["code"]: acc for acc in chart_accounts}

        system_prompt_obj = self._system_prompt_repo.get_active()
        system_prompt = system_prompt_obj.content if system_prompt_obj else _DEFAULT_SYSTEM_PROMPT
        logger.info("LLM system_prompt for doc=%s: %s", document_id, system_prompt)

        user_prompt = self._build_prompt(document, details, chart_accounts)

        ai_response = await self._ai.complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        raw_content: str = ai_response.get("content", "")
        logger.info("LLM raw_response for doc=%s: %s", document_id, raw_content)

        assignments, parse_warnings = self._parse_response(raw_content, details, puc_index)
        warnings.extend(parse_warnings)

        if not assignments:
            return {"assigned": 0, "skipped": len(details), "warnings": warnings}

        updated = await self._document_client.patch_detail_codes(document_id, assignments)

        skipped = len(details) - updated
        return {"assigned": updated, "skipped": skipped, "warnings": warnings}

    def _build_prompt(self, document: dict, details: list[dict], chart_accounts: list[dict]) -> str:
        """Construye el prompt de usuario con los ítems y el catálogo PUC filtrado.

        Se envía el catálogo completo (solo cuentas que aceptan movimientos) para que
        el LLM pueda elegir cualquier código válido. Filtrar aquí ahorraría tokens pero
        requeriría lógica de pre-clasificación que es exactamente lo que delega al LLM.
        """
        items = [
            {
                "item_id": d["id"],
                "description": d.get("description", ""),
                "type": d.get("type", "Account"),
            }
            for d in details
        ]

        puc_entries = [
            {"code": a.get("code"), "name": a.get("name")}
            for a in chart_accounts
            if a.get("accepts_movements", True)
        ]

        prompt_data: dict = {
            "items": items,
            "chart_accounts": puc_entries,
        }

        return json.dumps(prompt_data, ensure_ascii=False, indent=2)

    def _parse_response(
        self, raw: str, details: list[dict], puc_index: dict
    ) -> tuple[list[dict], list[str]]:
        """Parsea la respuesta del LLM y valida cada asignación contra el PUC local.

        El fallback con regex extrae el primer bloque {...} del texto porque algunos
        modelos ignoran la instrucción de responder solo JSON y envuelven la respuesta
        en markdown (```json ... ```). Acepta tanto "items" como "assignments" como
        clave raíz por retrocompatibilidad con versiones anteriores del prompt.
        """
        warnings: list[str] = []
        valid_detail_ids = {d["id"] for d in details}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Intentar extraer JSON del texto
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                warnings.append("El LLM no retornó JSON válido")
                return [], warnings
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                warnings.append("No se pudo parsear la respuesta del LLM")
                return [], warnings

        raw_assignments = parsed.get("assignments") or parsed.get("items", [])
        valid: list[dict] = []

        for item in raw_assignments:
            detail_id = item.get("item_id")
            code = str(item.get("code") or item.get("suggested_account_code", "")).strip()
            item_type = item.get("type", "Account")

            try:
                detail_id = int(detail_id)
            except (TypeError, ValueError):
                warnings.append(f"detail_id inválido: {detail_id!r}")
                continue

            if detail_id not in valid_detail_ids:
                warnings.append(f"detail_id {detail_id} no existe en el documento")
                continue

            if puc_index and code not in puc_index:
                warnings.append(
                    f"Código {code!r} no existe en el PUC local — detalle {detail_id} omitido"
                )
                continue

            if item_type not in ("Account", "Product", "FixedAsset"):
                item_type = "Account"

            valid.append({"detail_id": detail_id, "code": code, "type": item_type})

        return valid, warnings
