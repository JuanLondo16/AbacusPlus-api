"""Cliente HTTP hacia siigo-service para la contabilización (RF-05).

A diferencia de los demás clientes de este servicio, este **no es best-effort**: un fallo no
se puede tragar con un warning. Si no sabemos qué pasó con la petición, el documento tiene
que quedar bloqueado, porque la alternativa es reenviar y duplicar un asiento contable real.

Por eso el cliente distingue tres desenlaces y los expone al caso de uso:

- éxito con id de SIIGO,
- fallo del que consta que SIIGO no creó nada (seguro reintentar),
- incertidumbre: timeout, red o respuesta ilegible (NO reintentar).
"""

import logging
import os
from typing import Any, Optional

import httpx

from app.domain.services.siigo_error_classifier import extract_siigo_codes
from app.infrastructure.config.accounting_settings import get_accounting_settings

logger = logging.getLogger(__name__)


class ParametersUnavailableError(Exception):
    """No se pudo consultar la plantilla de parámetros; distinto de que no exista.

    La diferencia importa para el usuario: «no hay plantilla» se resuelve configurándola,
    «no se pudo consultar» se resuelve mirando el servicio o la sesión. Un mensaje único
    para ambos casos manda a configurar algo que quizá ya estaba bien.
    """


class PurchaseInvoiceResult:
    """Desenlace de un intento de contabilización, con la evidencia sin interpretar.

    Este objeto **no decide** si el fallo es reintentable ni qué debe hacer el usuario. Lleva
    lo que hace falta para decidirlo —código HTTP, códigos de error de SIIGO, cuerpo de la
    respuesta y si hubo respuesta siquiera— y la decisión la toma el clasificador, que es el
    único sitio del sistema con esa competencia.

    La versión anterior traía un booleano `safe_to_retry` calculado aquí dentro. El problema
    no era el booleano sino tener la regla repartida: la misma decisión se tomaba en dos
    capas, con criterios que discrepaban entre sí —una consideraba seguro reenviar tras un
    500 y la otra no—, y el veredicto que acababa ganando dependía de por dónde hubiera
    entrado el error. Con una sola fuente, esa discrepancia no puede reaparecer.
    """

    def __init__(
        self,
        ok: bool,
        siigo_id: Optional[str] = None,
        siigo_name: Optional[str] = None,
        error: Optional[str] = None,
        status_code: Optional[int] = None,
        siigo_codes: Optional[list] = None,
        response_body: Optional[dict] = None,
        #: True cuando no hubo respuesta legible de SIIGO: timeout, corte de red, cuerpo
        #: ilegible o un 2xx sin identificador. Es el caso en el que no se sabe nada, y por
        #: tanto el único en el que reintentar puede duplicar un asiento real.
        no_response: bool = False,
        #: True cuando el fallo lo produjo la validación previa de Abacus, sin llegar a
        #: llamar a SIIGO. Es la certeza opuesta: consta que no se creó nada.
        local_validation: bool = False,
    ):
        self.ok = ok
        self.siigo_id = siigo_id
        self.siigo_name = siigo_name
        self.error = error
        self.status_code = status_code
        self.siigo_codes = siigo_codes or []
        self.response_body = response_body
        self.no_response = no_response
        self.local_validation = local_validation


class PurchaseInvoiceLookup:
    """Resultado de preguntar a SIIGO si una factura de compra ya existe (RF-06).

    `consulted` es la propiedad que importa para la seguridad contable: cuando es False no se
    sabe nada, y «no se sabe» nunca puede tratarse como «no existe». Solo con `consulted=True`
    y `matches` vacío consta que SIIGO no creó la factura y el reenvío es seguro.
    """

    def __init__(
        self,
        consulted: bool,
        matches: Optional[list[dict[str, Any]]] = None,
        error: Optional[str] = None,
    ):
        self.consulted = consulted
        self.matches = matches or []
        self.error = error

    @property
    def found(self) -> bool:
        return self.consulted and bool(self.matches)

    @property
    def confirmed_absent(self) -> bool:
        """True solo si SIIGO respondió y no tiene la factura."""
        return self.consulted and not self.matches


class SiigoServiceClient:
    def __init__(
        self,
        base_url: str,
        bearer_token: str = "",
        timeout: Optional[float] = None,
        *,
        tenant_slug: Optional[str] = None,
    ):
        """Cliente hacia siigo-service.

        Admite las dos formas de autenticarse que tiene el sistema, y la elección no es
        arbitraria: depende de quién origina la llamada.

        - **Con `bearer_token`** — la llamada nace de una petición del usuario y viaja con su
          identidad. Es el camino del envío individual.
        - **Con `tenant_slug`** — la llamada nace de un worker de la cola, que no tiene
          usuario: se despierta solo, quizá minutos después de encolarse el documento, y para
          entonces el token de quien lo encoló puede haber vencido. Se usa el mismo patrón
          interno (`X-Internal-Secret` + `X-Tenant-Slug`) que ya emplean rag-service e
          integration-config-service para el trabajo en segundo plano.

        Persistir el token del usuario en la cola para reutilizarlo después habría sido la
        alternativa fácil y es peor: un JWT guardado en base de datos sobrevive al cierre de
        sesión de su dueño y convierte la tabla de la cola en un almacén de credenciales.
        """
        self._base_url = base_url.rstrip("/")
        self._tenant_slug = tenant_slug
        if tenant_slug:
            self._headers = {
                "X-Internal-Secret": os.getenv("INTERNAL_SECRET", ""),
                "X-Tenant-Slug": tenant_slug,
            }
        else:
            self._headers = (
                {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
            )
        # El timeout sale de la configuración y no de una constante del módulo. Debe superar
        # al que siigo-service usa contra SIIGO, para que sea SIIGO —y no este salto interno—
        # quien decida el desenlace: cortar antes es exactamente lo que fabrica la duda que
        # después obliga a reconciliar.
        self._timeout = (
            timeout if timeout is not None else get_accounting_settings().client_timeout_seconds
        )

    def _url(self, recurso: str) -> str:
        """Ruta del recurso, según el modo de autenticación.

        Las rutas internas son distintas de las públicas porque el gateway no expone las
        primeras. Resolverlo aquí, en un solo sitio, evita que cada método tenga que saber en
        qué modo está el cliente.
        """
        prefijo = "/internal/siigo" if self._tenant_slug else "/api/v1/siigo"
        return f"{self._base_url}{prefijo}/{recurso}"

    def get_purchase_invoice_parameters(
        self, account_key: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """Plantilla con los identificadores de catálogo que SIIGO exige.

        Es la fuente de los datos que no viven en el documento de la DIAN —el tipo de
        comprobante, la sucursal, la forma de pago por defecto— y que por tanto no pueden
        deducirse ni inventarse. Devuelve None si no hay plantilla, y el caso de uso detiene
        el envío con un mensaje explícito en lugar de improvisar valores.

        Sin `account_key` se piden las plantillas de todas las cuentas y se toma la primera
        activa. Filtrar por «default» era un error: el `account_key` lo elige cada cliente al
        registrar su credencial —'Ikbo', 'empresa-principal'— y una plantilla registrada con
        cualquier otra clave quedaba invisible, con el sistema informando que no existía.
        """
        url = self._url("purchase-invoice-parameters")
        try:
            response = httpx.get(
                url,
                params={"account_key": account_key} if account_key else None,
                headers=self._headers,
                timeout=15.0,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            # Se distingue de «no hay plantilla» a propósito. Confundir ambos casos manda al
            # usuario a configurar algo que quizá ya está configurado, mientras el problema
            # real —un token vencido, el servicio caído— queda invisible.
            raise ParametersUnavailableError(
                f"No se pudo consultar la plantilla de parámetros: siigo-service respondió "
                f"{exc.response.status_code}. Verifique que el servicio esté disponible y "
                f"que la sesión siga siendo válida."
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ParametersUnavailableError(
                f"No se pudo consultar la plantilla de parámetros: {exc}. Verifique que "
                f"siigo-service esté disponible."
            ) from exc

        plantillas = body if isinstance(body, list) else body.get("results") or []
        activas = [p for p in plantillas if p.get("active", True)]

        if not activas:
            return None

        if len(activas) > 1 and account_key is None:
            # Elegir «la primera» sería una lotería con consecuencias contables: cada
            # plantilla lleva su propio `account_key`, y ese decide contra qué empresa de
            # SIIGO se crea la factura. Con varias activas no hay forma de saber cuál quiso
            # el contador, así que se detiene el envío y se le pide que lo precise.
            nombres = ", ".join(
                f"{p.get('name')} ({p.get('account_key')})" for p in activas[:5]
            )
            raise ParametersUnavailableError(
                "Hay varias plantillas de parámetros de factura de compra activas y no se "
                f"puede determinar cuál usar: {nombres}. Deje activa solo la que "
                "corresponda a la empresa en la que se debe contabilizar."
            )

        return activas[0]

    def find_purchase_invoice(
        self, provider_invoice_number: str, document_date: Optional[str] = None
    ) -> "PurchaseInvoiceLookup":
        """RF-06: pregunta a SIIGO si la factura de compra ya existe.

        Es la única salida legítima del estado «Contabilizando». Aquí importa distinguir tres
        desenlaces y no dos: encontrada, no encontrada, y **no se pudo averiguar**. Confundir
        el tercero con el segundo es lo que llevaría a reenviar un documento que sí se creó,
        así que un fallo de consulta nunca se traduce en «no existe».
        """
        url = self._url("purchase-invoices")
        params: dict[str, Any] = {"provider_invoice_number": provider_invoice_number}
        if document_date:
            params["document_date"] = document_date

        try:
            response = httpx.get(url, params=params, headers=self._headers, timeout=60.0)
        except httpx.HTTPError as exc:
            logger.error("No se pudo consultar SIIGO para reconciliar: %s", exc)
            return PurchaseInvoiceLookup(
                consulted=False,
                error=(
                    "No fue posible consultar SIIGO para verificar si la factura existe. "
                    "Intente de nuevo; no reenvíe el documento sin comprobarlo."
                ),
            )

        if response.status_code != 200:
            detalle: Any = None
            try:
                detalle = response.json().get("detail")
            except ValueError:
                detalle = response.text[:300]
            mensaje = (
                detalle.get("message")
                if isinstance(detalle, dict)
                else str(detalle or f"SIIGO respondió {response.status_code}.")
            )
            return PurchaseInvoiceLookup(consulted=False, error=mensaje)

        try:
            cuerpo = response.json()
        except ValueError:
            return PurchaseInvoiceLookup(
                consulted=False, error="La respuesta de la consulta a SIIGO no pudo leerse."
            )

        return PurchaseInvoiceLookup(
            consulted=True, matches=list(cuerpo.get("matches") or [])
        )

    def create_purchase_invoice(self, payload: dict[str, Any]) -> PurchaseInvoiceResult:
        """Crea la factura de compra en SIIGO a través de siigo-service.

        Es síncrono a propósito: la transición de estado del documento depende del resultado,
        así que no hay nada que adelantar mientras se espera.

        Lo único que hace este método es traducir «qué pasó en el cable» a un objeto con la
        evidencia intacta. No clasifica, no decide reintentos y no toca el documento. Todo
        camino que no termine con un identificador de SIIGO en la mano acaba en un resultado
        marcado como `no_response`, que es la forma de decir «no sabemos» — y «no sabemos»
        nunca puede degradarse a «no se creó».
        """
        url = self._url("purchase-invoices")
        try:
            response = httpx.post(
                url, json=payload, headers=self._headers, timeout=self._timeout
            )
        except httpx.TimeoutException:
            # La petición pudo llegar a SIIGO y crear la factura sin que veamos la respuesta.
            logger.error("Timeout al contabilizar en SIIGO; el documento queda bloqueado")
            return PurchaseInvoiceResult(
                ok=False,
                error=(
                    "SIIGO no respondió a tiempo. La factura pudo haberse creado: "
                    "verifíquela en SIIGO antes de reenviar el documento."
                ),
                no_response=True,
            )
        except httpx.HTTPError as exc:
            logger.error("Error de red al contabilizar en SIIGO: %s", exc)
            return PurchaseInvoiceResult(
                ok=False,
                error=(
                    "No fue posible comunicarse con SIIGO. La factura pudo haberse creado: "
                    "verifíquela en SIIGO antes de reenviar el documento."
                ),
                no_response=True,
            )

        if response.status_code in (200, 201):
            try:
                body = response.json()
            except ValueError:
                return PurchaseInvoiceResult(
                    ok=False,
                    error=(
                        "SIIGO aceptó la petición pero la respuesta no pudo leerse. "
                        "Verifique en SIIGO antes de reenviar."
                    ),
                    status_code=response.status_code,
                    no_response=True,
                )
            siigo_id = body.get("siigo_id")
            if not siigo_id:
                # Sin id no hay prueba de qué se creó: se bloquea en lugar de darlo por bueno.
                return PurchaseInvoiceResult(
                    ok=False,
                    error=(
                        "SIIGO no devolvió el identificador del comprobante. "
                        "Verifique en SIIGO antes de reenviar."
                    ),
                    status_code=response.status_code,
                    response_body=body if isinstance(body, dict) else None,
                    no_response=True,
                )
            return PurchaseInvoiceResult(
                ok=True,
                siigo_id=str(siigo_id),
                siigo_name=body.get("siigo_name"),
                status_code=response.status_code,
                response_body=body if isinstance(body, dict) else None,
            )

        return self._failure_from_response(response)

    @staticmethod
    def _failure_from_response(response: httpx.Response) -> PurchaseInvoiceResult:
        """Extrae la evidencia de un error de siigo-service, sin interpretarla.

        Se conserva `siigo_did_not_create` cuando siigo-service lo envía, pero ya no como un
        veredicto que sustituye al criterio propio: sirve para descartar como incierto un
        fallo que siigo-service sabe que sí llegó a SIIGO. Quien decide la clase del error a
        partir del código HTTP y de los códigos de SIIGO es el clasificador, en un solo sitio.
        """
        detail: Any = None
        cuerpo: Optional[dict] = None
        try:
            cuerpo = response.json()
            detail = cuerpo.get("detail") if isinstance(cuerpo, dict) else None
        except ValueError:
            detail = response.text[:500]

        codigos: list = []
        message: str
        no_response = False

        if isinstance(detail, dict):
            message = str(detail.get("message") or "SIIGO rechazó el documento.")
            codigos = extract_siigo_codes(detail)
            if detail.get("duplicate"):
                # SIIGO afirma que el comprobante ya existe. El clasificador lo tratará como
                # duplicado aunque el código no viniera en la lista.
                codigos = list(codigos) + ["duplicated_document"]
            # Si siigo-service afirma explícitamente que SIIGO NO llegó a crear nada, se
            # respeta esa afirmación —él fue quien habló con SIIGO—; pero solo puede añadir
            # certeza, nunca quitarla: un `False` aquí es «no consta», y eso ya es lo que el
            # clasificador deduce por su cuenta a partir del código HTTP.
            veredicto = detail.get("siigo_did_not_create")
            if veredicto is False and response.status_code >= 500:
                no_response = True
        else:
            message = str(detail or f"SIIGO respondió {response.status_code}.")

        return PurchaseInvoiceResult(
            ok=False,
            error=message,
            status_code=response.status_code,
            siigo_codes=codigos,
            response_body=cuerpo if isinstance(cuerpo, dict) else None,
            no_response=no_response,
        )
