"""Diagnóstico fiscal: contrasta la configuración de Abacus con la de SIIGO.

Es una operación de **solo lectura**. No escribe nada en SIIGO, y no por comodidad: la
configuración de la empresa y del comprobante no es escribible —los nueve recursos del grupo
«Catálogos» exponen únicamente `GET`— y el maestro de terceros, que sí admite `PUT`, reemplaza
el registro completo y perdería campos que el `GET` no devuelve.

Lo que sí aporta es responder, dentro de la aplicación, por qué una retención no se está
practicando: hasta ahora eso se descubría documento a documento, tras el rechazo de SIIGO.

Sobre el consumo de la API
---------------------------
SIIGO limita a 100 peticiones por minuto y por empresa. El diagnóstico consulta un tercero por
NIT, así que con 38 proveedores gasta 39 peticiones —una por tercero más la del comprobante—.
Por eso `solo_con_diferencias` viene activado y existe `limite`: el informe habitual interesa
por lo que no cuadra, no por la lista completa.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.domain.exceptions.base import EntityNotFoundException
from app.domain.services.fiscal_diagnosis import comparar_empresa, comparar_tercero
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.clients.siigo_rate_limiter import limitador_siigo

logger = logging.getLogger(__name__)

_SIIGO_PROVIDER = "siigo"
_DOCUMENT_TYPES_PATH = "/v1/document-types?type=FC"
_CUSTOMERS_PATH = "/v1/customers?identification={nit}"

#: Tope por defecto de terceros consultados. Cada uno gasta una petición del cupo por minuto.
LIMITE_POR_DEFECTO = 40


@dataclass
class ResultadoDiagnostico:
    generado_en: datetime
    #: None si no se pudo consultar el comprobante en SIIGO.
    comprobante_id: Optional[int] = None
    empresa: list = field(default_factory=list)
    terceros: list = field(default_factory=list)
    terceros_revisados: int = 0
    #: Motivos por los que el diagnóstico está incompleto, para no presentarlo como concluyente.
    advertencias: list = field(default_factory=list)


class DiagnoseFiscalSetupUseCase:
    def __init__(self, credential_repository, fiscal_profile_repository, db):
        self.credential_repository = credential_repository
        self.fiscal_profile_repository = fiscal_profile_repository
        self.db = db

    def execute(
        self, solo_con_diferencias: bool = True, limite: int = LIMITE_POR_DEFECTO
    ) -> ResultadoDiagnostico:
        credenciales = self.credential_repository.list(provider=_SIIGO_PROVIDER)
        if not credenciales:
            raise EntityNotFoundException("IntegrationCredential", "siigo")

        credencial = credenciales[0]
        cliente = SiigoApiClient(credencial)
        self._asegurar_token(cliente, credencial.account_key)

        resultado = ResultadoDiagnostico(generado_en=datetime.now(timezone.utc))

        comprobante = self._comprobante_de_compra(cliente, resultado)
        if comprobante:
            resultado.comprobante_id = comprobante.get("id")

        resultado.empresa = comparar_empresa(self.fiscal_profile_repository.get(), comprobante)
        self._revisar_terceros(cliente, resultado, solo_con_diferencias, limite)
        return resultado

    # ── Empresa ───────────────────────────────────────────────────────────────

    def _comprobante_de_compra(self, cliente, resultado) -> Optional[dict]:
        """El tipo de comprobante de compra configurado, o None si no se pudo consultar.

        Se toma el primero activo cuando la plantilla no fija uno: es el que usará el envío.
        """
        try:
            tipos = SiigoApiClient._extract_results(cliente.get(_DOCUMENT_TYPES_PATH))
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo consultar el comprobante de compra en SIIGO: %s", exc)
            resultado.advertencias.append(
                "No se pudo consultar la configuración del comprobante en SIIGO; las "
                "retenciones de la empresa no se contrastaron."
            )
            return None

        fila = self.db.execute(
            text("SELECT document_id FROM purchase_invoice_parameters LIMIT 1")
        ).first()
        configurado = fila[0] if fila else None

        if configurado:
            for tipo in tipos:
                if str(tipo.get("id")) == str(configurado):
                    return tipo
            resultado.advertencias.append(
                f"El comprobante {configurado} de la plantilla no aparece entre los tipos de "
                "compra de SIIGO."
            )
        return next((t for t in tipos if t.get("active")), None)

    # ── Terceros ──────────────────────────────────────────────────────────────

    def _revisar_terceros(self, cliente, resultado, solo_con_diferencias, limite) -> None:
        filas = self.db.execute(
            text(
                "SELECT nit, name, tipo_contribuyente FROM issuers "
                "WHERE nit IS NOT NULL AND nit <> '' ORDER BY name"
            )
        ).fetchall()

        for nit, nombre, tipo in filas[: max(0, int(limite or 0))]:
            tercero = self._tercero_en_siigo(cliente, nit)
            if tercero is _NO_CONSULTADO:
                resultado.advertencias.append(
                    f"No se pudo consultar el tercero {nit} en SIIGO; queda sin contrastar."
                )
                continue

            resultado.terceros_revisados += 1
            diferencia = comparar_tercero(nit, nombre, tipo, tercero)
            if diferencia.coincide and solo_con_diferencias:
                continue
            resultado.terceros.append(diferencia)

        if len(filas) > limite:
            resultado.advertencias.append(
                f"Se revisaron {limite} de {len(filas)} terceros. SIIGO limita a 100 "
                "peticiones por minuto; suba el límite para revisar el resto."
            )

    def _tercero_en_siigo(self, cliente, nit):
        """El tercero, None si no existe allí, o `_NO_CONSULTADO` si la consulta falló.

        Los tres casos se distinguen a propósito: «no existe» es un hallazgo del diagnóstico,
        mientras que «no se pudo consultar» es una laguna del propio informe, y presentarlos
        igual haría creer que faltan terceros que en realidad no se llegaron a comprobar.
        """
        # Una petición por proveedor: el limitador reparte el cupo que SIIGO concede por minuto.
        # Con un catálogo pequeño no llega a esperar —la ráfaga lo absorbe entero—; con uno
        # grande el diagnóstico tarda más en lugar de provocar un 429, que además de perder la
        # petición suma a la proporción de errores por la que SIIGO bloquea la cuenta.
        limitador_siigo.acquire()
        try:
            encontrados = SiigoApiClient._extract_results(
                cliente.get(_CUSTOMERS_PATH.format(nit=nit))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo consultar el tercero %s en SIIGO: %s", nit, exc)
            return _NO_CONSULTADO
        return encontrados[0] if encontrados else None

    # ── Autenticación ─────────────────────────────────────────────────────────

    def _asegurar_token(self, cliente: SiigoApiClient, account_key: str) -> None:
        credencial = cliente.credential
        ahora = datetime.now(timezone.utc)
        expira = credencial.expires_at
        if expira and expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        if credencial.access_token and expira and expira > ahora:
            return

        respuesta = cliente.authenticate()
        nueva_expiracion = token_expiration_from_response(respuesta)
        credencial.access_token = respuesta["access_token"]
        credencial.token_type = respuesta.get("token_type", "Bearer")
        credencial.expires_at = nueva_expiracion
        self.credential_repository.save_token(
            provider=_SIIGO_PROVIDER,
            account_key=account_key,
            access_token=respuesta["access_token"],
            token_type=respuesta.get("token_type", "Bearer"),
            expires_at=nueva_expiracion,
        )


#: Centinela: distingue «el tercero no existe en SIIGO» de «no se pudo consultar».
_NO_CONSULTADO = object()
