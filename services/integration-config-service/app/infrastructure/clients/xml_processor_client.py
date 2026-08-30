import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


class XmlProcessorClient:
    """Cliente del endpoint interno de xml-processor.

    `cost_centers` es propiedad de xml-processor —es la tabla que alimenta el catálogo que
    consume el frontend—, por lo que la proyección del catálogo sincronizado se delega a ese
    servicio en lugar de escribir su tabla directamente.
    """

    def __init__(self, base_url: Optional[str] = None, secret: Optional[str] = None):
        self._base_url = (base_url or os.environ.get("XML_PROCESSOR_URL", "")).rstrip("/")
        self._secret = secret if secret is not None else os.environ.get("INTERNAL_SECRET", "")

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._secret)

    def project_puc_accounts(
        self, tenant_slug: str, items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Proyecta el plan de cuentas importado sobre el catálogo de xml-processor."""
        return self._project("puc-accounts", tenant_slug, items)

    def project_cost_centers(
        self, tenant_slug: str, items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Proyecta los centros de costo sincronizados sobre el catálogo de xml-processor.

        Retorna el resumen de la proyección, o `None` si el cliente no está configurado o la
        llamada falla. La sincronización no se revierte por un fallo de proyección: los datos
        quedan en `integration_cost_centers` y la operación es idempotente, así que puede
        reintentarse.
        """
        return self._project("cost-centers", tenant_slug, items)

    def _project(
        self, resource: str, tenant_slug: str, items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logger.warning(
                "XmlProcessorClient sin configurar (XML_PROCESSOR_URL/INTERNAL_SECRET); "
                "se omite la proyección de %s",
                resource,
            )
            return None

        try:
            response = httpx.post(
                f"{self._base_url}/internal/catalog/{resource}/projections",
                json=items,
                headers={
                    "x-internal-secret": self._secret,
                    "x-tenant-slug": tenant_slug,
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Fallo proyectando %s en xml-processor: %s", resource, exc)
            return None
