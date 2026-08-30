"""RF-05: clasificación de los fallos de contabilización de SIIGO.

Este módulo es el **único** sitio del sistema que decide qué significa un error de SIIGO. Su
salida —clase y acción recomendada— viaja hasta el frontend, que se limita a pintar el botón
correspondiente sin conocer un solo código de SIIGO.

Cómo añadir un error nuevo
--------------------------
Se agrega **una fila** a `_REGLAS_POR_CODIGO`. Nada más: ni el caso de uso, ni la cola, ni
los endpoints, ni el frontend necesitan cambiar. Ése es todo el objetivo del diseño: la
lista de errores de SIIGO va a crecer a medida que se descubran en producción, y ese
crecimiento no puede exigir tocar siete componentes cada vez.

De dónde salen las reglas
-------------------------
De la documentación oficial de SIIGO (sección «Manejo de errores»), que publica el catálogo
de códigos con su HTTP status. Los códigos que solo se conocen por observación —los que
devuelve /v1/purchases al rechazar una cuenta PUC o una retención concreta— se marcan como
PENDIENTE DE CONFIRMACIÓN: el fallback por HTTP status los cubre razonablemente mientras
tanto, pero la fila explícita da un mensaje mucho mejor.

La regla de oro
---------------
Ante la duda, `UNCERTAIN`. Clasificar de menos —tratar como incierto algo que en realidad
era inocuo— cuesta una verificación manual. Clasificar de más —tratar como seguro algo
ambiguo— cuesta un asiento contable duplicado en la contabilidad real de un cliente. Los dos
errores no son simétricos, y esta jerarquía se inclina siempre hacia el primero.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.domain.value_objects.accounting_error import ErrorClass, RecommendedAction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorClassification:
    """Veredicto sobre un fallo concreto."""

    error_class: str
    recommended_action: str
    #: Mensaje dirigido al contador: nombra el dato a corregir, no la excepción técnica.
    message: str
    #: Código de SIIGO que originó la clasificación, si lo hubo. Se audita.
    siigo_code: Optional[str] = None
    #: True si la cola puede reintentar sola. Es distinto de que el usuario pueda reintentar:
    #: un error corregible es reenviable por el usuario, pero nunca automáticamente.
    auto_retryable: bool = False


@dataclass(frozen=True)
class _Regla:
    """Una fila de la tabla de clasificación."""

    error_class: str
    recommended_action: str
    #: Explicación orientada a la acción. Se antepone al mensaje literal de SIIGO, que se
    #: conserva siempre: el contador necesita saber qué hacer, y el soporte qué dijo SIIGO.
    hint: str
    auto_retryable: bool = False


# ── Reglas por código de error de SIIGO ────────────────────────────────────────
#
# La clave es el `Code` del cuerpo de error de SIIGO, en minúsculas.
_REGLAS_POR_CODIGO: dict[str, _Regla] = {
    # ── Reintentables: consta que SIIGO no procesó la petición ─────────────────
    "requests_limit": _Regla(
        ErrorClass.RATE_LIMIT,
        RecommendedAction.RETRY,
        "Se superó el límite de peticiones por minuto de SIIGO. El envío se reintenta solo "
        "tras una espera; no es necesario corregir nada.",
        auto_retryable=True,
    ),
    "service_unavailable": _Regla(
        ErrorClass.TRANSIENT,
        RecommendedAction.RETRY,
        "SIIGO no está disponible en este momento. El envío se reintenta solo; no es "
        "necesario corregir nada.",
        auto_retryable=True,
    ),
    # ── Inciertos: SIIGO pudo haber creado la factura ──────────────────────────
    #
    # `unhandled_error` y `request_timeout` son los dos casos en los que la documentación de
    # SIIGO no permite afirmar en qué punto se interrumpió el proceso. Un 500 puede
    # significar «falló antes de tocar la contabilidad» o «creó el comprobante y falló
    # después», y /v1/purchases no ofrece idempotencia para distinguirlo. Reintentar a
    # ciegas duplicaría un asiento real.
    "unhandled_error": _Regla(
        ErrorClass.UNCERTAIN,
        RecommendedAction.RECONCILE,
        "SIIGO respondió con un error interno y no se sabe si la factura llegó a crearse. "
        "Verifique en SIIGO antes de reenviar.",
    ),
    "request_timeout": _Regla(
        ErrorClass.UNCERTAIN,
        RecommendedAction.RECONCILE,
        "SIIGO no respondió a tiempo y la factura pudo haberse creado. Verifique en SIIGO "
        "antes de reenviar.",
    ),
    # ── Duplicado: la factura YA existe ────────────────────────────────────────
    "duplicated_document": _Regla(
        ErrorClass.DUPLICATE,
        RecommendedAction.RECONCILE,
        "SIIGO informa que este comprobante ya existe. No lo reenvíe: verifíquelo para "
        "cerrar el documento con la factura que ya está creada.",
    ),
    # ── Configuración / credenciales: el documento está bien ───────────────────
    "unauthorized": _Regla(
        ErrorClass.CONFIG,
        RecommendedAction.FIX_CONFIGURATION,
        "Las credenciales de SIIGO no son válidas o el usuario API está bloqueado. Revise "
        "la integración; el documento no necesita cambios.",
    ),
    "invalid_partner_id": _Regla(
        ErrorClass.CONFIG,
        RecommendedAction.FIX_CONFIGURATION,
        "El identificador de socio (Partner-Id) configurado en la integración no es válido. "
        "Revise la integración; el documento no necesita cambios.",
    ),
    # ── Corregibles: SIIGO rechazó un dato, sin crear nada ─────────────────────
    "parameter_required": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "Falta un dato obligatorio para SIIGO. Complételo en la causación y vuelva a enviar.",
    ),
    "invalid_reference": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO no reconoce uno de los datos referenciados —cuenta PUC, centro de costo, "
        "impuesto, retención o tercero—. Corríjalo en la causación y vuelva a enviar.",
    ),
    "invalid_code": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "Un código enviado a SIIGO no tiene un formato válido. Corríjalo en la causación y "
        "vuelva a enviar.",
    ),
    "invalid_amount": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "Un valor monetario está fuera del rango que SIIGO admite. Revise las cantidades y "
        "los precios de la causación.",
    ),
    "invalid_total_payments": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "La suma de las formas de pago no coincide con el total del documento. Revise la "
        "forma de pago y las retenciones de la causación.",
    ),
    "invalid_date": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO rechazó una fecha del documento, normalmente por estar fuera del periodo "
        "contable abierto. Revise la fecha del documento y el periodo en SIIGO.",
    ),
    "invalid_type": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO rechazó el formato de uno de los datos enviados. Es un problema de la "
        "integración, no de la causación: repórtelo si persiste tras reintentar.",
    ),
    "invalid_array": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO rechazó una de las listas enviadas —ítems, impuestos o retenciones—. Revise "
        "las líneas y las retenciones de la causación.",
    ),
    "invalid_identification": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "El NIT del proveedor no tiene un formato válido o el tercero no existe en SIIGO. "
        "Verifique el tercero antes de reenviar.",
    ),
    "invalid_email": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "Un correo electrónico enviado a SIIGO no tiene un formato válido.",
    ),
    "not_found": _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO no encuentra uno de los elementos referenciados por el documento. Verifique "
        "que la cuenta, el impuesto o el centro de costo existan y estén activos en SIIGO.",
    ),
}


# ── Fallback por HTTP status ───────────────────────────────────────────────────
#
# Se usa cuando SIIGO no devuelve un `Code` reconocible —una respuesta no JSON, un error del
# gateway intermedio, un código nuevo aún no catalogado—.
#
# La composición de esta tabla es donde estaba el defecto más grave de la implementación
# anterior: 500, 502 y 504 se consideraban seguros para reenviar. No lo son. Un 5xx de SIIGO
# es indistinguible entre «falló antes de crear» y «creó y falló después», y sin idempotencia
# en /v1/purchases esa ambigüedad es exactamente un duplicado en potencia.
_REGLAS_POR_STATUS: dict[int, _Regla] = {
    400: _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO rechazó los datos del documento sin crear nada. Corrija la causación y "
        "vuelva a enviar.",
    ),
    401: _Regla(
        ErrorClass.CONFIG,
        RecommendedAction.FIX_CONFIGURATION,
        "SIIGO rechazó las credenciales de la integración.",
    ),
    403: _Regla(
        ErrorClass.CONFIG,
        RecommendedAction.FIX_CONFIGURATION,
        "El usuario de SIIGO no tiene permiso para esta operación.",
    ),
    404: _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "SIIGO no encuentra alguno de los elementos referenciados por el documento.",
    ),
    408: _Regla(
        ErrorClass.UNCERTAIN,
        RecommendedAction.RECONCILE,
        "SIIGO cortó la petición por tiempo y la factura pudo haberse creado. Verifique en "
        "SIIGO antes de reenviar.",
    ),
    409: _Regla(
        ErrorClass.DUPLICATE,
        RecommendedAction.RECONCILE,
        "SIIGO informa un conflicto con un comprobante existente. Verifíquelo antes de "
        "reenviar.",
    ),
    422: _Regla(
        ErrorClass.CORRECTABLE,
        RecommendedAction.EDIT_AND_RETRY,
        "Falta información obligatoria en la causación. Corríjala y vuelva a enviar.",
    ),
    429: _Regla(
        ErrorClass.RATE_LIMIT,
        RecommendedAction.RETRY,
        "Se superó el límite de peticiones por minuto de SIIGO. Se reintenta tras una espera.",
        auto_retryable=True,
    ),
    503: _Regla(
        ErrorClass.TRANSIENT,
        RecommendedAction.RETRY,
        "SIIGO no está disponible en este momento. Se reintenta solo.",
        auto_retryable=True,
    ),
}

#: Desenlace por defecto de cualquier 5xx no catalogado. Ver el comentario de arriba: la
#: ambigüedad de un 5xx es la razón de existir de esta constante.
_REGLA_5XX = _Regla(
    ErrorClass.UNCERTAIN,
    RecommendedAction.RECONCILE,
    "SIIGO falló de forma que no permite saber si la factura llegó a crearse. Verifique en "
    "SIIGO antes de reenviar.",
)

#: Desenlace cuando no hay ni código ni status: timeout del cliente, corte de red durante la
#: espera, cuerpo ilegible, 2xx sin identificador. En todos, la petición pudo haber llegado.
_REGLA_SIN_RESPUESTA = _Regla(
    ErrorClass.UNCERTAIN,
    RecommendedAction.RECONCILE,
    "No se obtuvo respuesta de SIIGO y la factura pudo haberse creado. Verifique en SIIGO "
    "antes de reenviar.",
)

#: Fallo de la validación previa de Abacus. Es el único caso en el que consta con certeza
#: absoluta que SIIGO no fue llamado, porque la llamada no llegó a salir de aquí.
_REGLA_VALIDACION_LOCAL = _Regla(
    ErrorClass.CORRECTABLE,
    RecommendedAction.EDIT_AND_RETRY,
    "El documento no tiene toda la información que SIIGO exige. Complétela en la causación "
    "y vuelva a enviar.",
)


# ── Pistas por texto ───────────────────────────────────────────────────────────
#
# SIIGO devuelve `invalid_reference` para cualquier referencia inválida, sin distinguir si
# era una cuenta PUC, un centro de costo o una retención. El `Message` sí lo dice, y ese
# matiz es lo que convierte «corrija algo» en «corrija la cuenta PUC de la línea 3».
#
# Solo afinan el MENSAJE. La clase y la acción ya vienen decididas por código o status, y
# nunca se derivan de aquí: hacer depender la seguridad contable de una coincidencia de
# texto —que SIIGO puede reescribir en cualquier momento— sería frágil justo donde no puede
# serlo.
_PISTAS_DE_TEXTO: tuple[tuple[str, str], ...] = (
    (r"\baccount\b|\bcuenta\b|\bpuc\b", "Revise la cuenta contable (PUC) de las líneas."),
    (r"cost.?cent|centro.?de.?costo", "Revise el centro de costo del documento."),
    (r"\btax\b|\bimpuesto\b|\biva\b", "Revise los impuestos de las líneas."),
    (r"retention|retencion|retención|rete", "Revise las retenciones del documento."),
    (
        r"supplier|proveedor|tercero|customer",
        "Revise el tercero (proveedor) del documento y que exista en SIIGO.",
    ),
    (r"payment|forma.?de.?pago|pago", "Revise la forma de pago del documento."),
    (r"document.?type|tipo.?de.?comprobante", "Revise el tipo de comprobante configurado."),
)


class SiigoErrorClassifier:
    """Traduce un fallo de SIIGO a una clase y a la acción que puede ofrecerse al usuario.

    Sin estado y sin dependencias: es una función de la respuesta a un veredicto. Eso lo hace
    trivial de probar con las respuestas reales que se capturen en las pruebas contra SIIGO,
    que es exactamente como debe validarse esta tabla.
    """

    def classify(
        self,
        *,
        status_code: Optional[int] = None,
        siigo_codes: Optional[list] = None,
        message: str = "",
        local_validation: bool = False,
        no_response: bool = False,
    ) -> ErrorClassification:
        """Clasifica un fallo.

        `local_validation` y `no_response` son los dos extremos de la certeza y por eso
        entran por su propia puerta en lugar de deducirse: en el primero consta que SIIGO no
        fue llamado; en el segundo, que no sabemos nada. Deducirlos de la ausencia de
        `status_code` los confundiría, y significan lo contrario el uno del otro.
        """
        if local_validation:
            return self._resultado(_REGLA_VALIDACION_LOCAL, message, None)

        if no_response:
            return self._resultado(_REGLA_SIN_RESPUESTA, message, None)

        codigo = self._primer_codigo_conocido(siigo_codes)
        if codigo is not None:
            return self._resultado(_REGLAS_POR_CODIGO[codigo], message, codigo)

        # Hay códigos, pero ninguno está catalogado. Se registra para poder añadirlo a la
        # tabla: es la señal de que SIIGO devuelve algo que todavía no sabemos interpretar.
        desconocidos = [str(c) for c in (siigo_codes or []) if c]
        if desconocidos:
            logger.warning(
                "RF-05: código de error de SIIGO sin clasificar %s (status=%s): %s",
                desconocidos,
                status_code,
                message,
            )

        primero = desconocidos[0] if desconocidos else None

        if status_code is None:
            return self._resultado(_REGLA_SIN_RESPUESTA, message, primero)

        regla = _REGLAS_POR_STATUS.get(int(status_code))
        if regla is not None:
            return self._resultado(regla, message, primero)

        if 500 <= int(status_code) < 600:
            return self._resultado(_REGLA_5XX, message, primero)

        # Un código HTTP fuera de todo lo previsto. No se presume nada.
        return self._resultado(
            _Regla(
                ErrorClass.UNKNOWN,
                RecommendedAction.MANUAL_REVIEW,
                f"SIIGO respondió con un código inesperado ({status_code}). Revise el "
                "documento manualmente antes de reenviarlo.",
            ),
            message,
            primero,
        )

    # ── Auxiliares ─────────────────────────────────────────────────────────────

    @staticmethod
    def _primer_codigo_conocido(siigo_codes: Optional[list]) -> Optional[str]:
        """Primer código catalogado de la lista.

        SIIGO puede devolver varios errores a la vez. Se toma el primero **conocido** y no
        el primero a secas, para que un código nuevo sin catalogar no eclipse a uno que sí
        sabemos interpretar y degrade la clasificación a UNKNOWN sin necesidad.
        """
        for code in siigo_codes or []:
            if code and str(code).strip().lower() in _REGLAS_POR_CODIGO:
                return str(code).strip().lower()
        return None

    def _resultado(
        self, regla: _Regla, message: str, siigo_code: Optional[str]
    ) -> ErrorClassification:
        return ErrorClassification(
            error_class=regla.error_class,
            recommended_action=regla.recommended_action,
            message=self._componer_mensaje(regla, message),
            siigo_code=siigo_code,
            auto_retryable=regla.auto_retryable,
        )

    def _componer_mensaje(self, regla: _Regla, message: str) -> str:
        """Junta la explicación accionable con lo que SIIGO dijo literalmente.

        Los dos hacen falta y no son intercambiables: la explicación le dice al contador qué
        hacer, y el texto de SIIGO es lo que permite al soporte entender un caso raro. Quedarse
        solo con el primero borraría la evidencia; solo con el segundo, dejaría al contador
        leyendo `invalid_reference` sin saber qué corregir.
        """
        partes = [regla.hint]

        pista = (
            self._pista_de_texto(message) if regla.error_class == ErrorClass.CORRECTABLE else None
        )
        if pista:
            partes.append(pista)

        literal = self._literal_legible(message)
        if literal and not self._es_marcador_propio(literal):
            partes.append(f"SIIGO informó: {literal}")

        return " ".join(partes)

    #: Lo que el cliente escribe cuando SIIGO **no** dijo nada legible: «SIIGO respondió 400.».
    #: Es un marcador nuestro, no una frase suya.
    _MARCADOR_PROPIO = re.compile(r"^siigo respondió\s+\d{3}\.?$", re.IGNORECASE)

    @classmethod
    def _es_marcador_propio(cls, literal: str) -> bool:
        """¿El «literal» es en realidad el relleno que pone `siigo_client`?

        Cuando la respuesta no trae ningún texto aprovechable, el cliente guarda
        «SIIGO respondió 400.» para que la auditoría no quede vacía. Eso sirve en el log,
        pero pegado detrás de «SIIGO informó:» produce «SIIGO informó: SIIGO respondió 400»:
        una frase que se atribuye a SIIGO sin que SIIGO haya dicho nada, y que además repite
        el código de estado que la explicación de delante ya ha traducido a lenguaje llano.

        Se descarta. Cuando SIIGO no dice nada, lo correcto es no ponerle palabras en la boca:
        queda la explicación accionable, que es la que el contador necesita, y el cuerpo crudo
        sigue íntegro en la auditoría del intento para quien tenga que diagnosticar.
        """
        return bool(cls._MARCADOR_PROPIO.match(literal.strip()))

    @staticmethod
    def _literal_legible(message: str) -> str:
        """La frase de SIIGO, no su sobre JSON.

        El cliente conserva el cuerpo crudo de la respuesta para que un 400 sin `Errors` no
        se quede sin diagnóstico. Eso es lo correcto para el log y para la auditoría, que
        guarda el cuerpo entero, pero pegado al mensaje del contador convierte una frase
        accionable en un volcado con llaves, comillas y URLs de documentación.

        Se extrae lo único que un contador puede leer —el `Message` de cada error— y se
        descarta el envoltorio. Si el texto no es JSON, se recorta: un mensaje de pantalla
        no es el sitio donde cabe una respuesta completa.
        """
        literal = (message or "").strip()
        if not literal:
            return ""

        inicio = literal.find("{")
        if inicio != -1:
            try:
                cuerpo = json.loads(literal[inicio:])
            except (ValueError, TypeError):
                cuerpo = None
            if isinstance(cuerpo, dict):
                frases = [
                    str(e.get("Message") or e.get("message") or "").strip()
                    for e in (cuerpo.get("Errors") or cuerpo.get("errors") or [])
                    if isinstance(e, dict)
                ]
                frases = [f for f in frases if f]
                if frases:
                    return "; ".join(dict.fromkeys(frases))
                literal = literal[:inicio].strip().rstrip(":").strip() or literal

        return literal[:200]

    @staticmethod
    def _pista_de_texto(message: str) -> Optional[str]:
        texto = (message or "").lower()
        for patron, pista in _PISTAS_DE_TEXTO:
            if re.search(patron, texto):
                return pista
        return None


#: Instancia compartida. El clasificador no tiene estado, así que una basta.
default_classifier = SiigoErrorClassifier()


def register_error_code(
    code: str,
    *,
    error_class: str,
    recommended_action: str,
    hint: str,
    auto_retryable: bool = False,
) -> None:
    """Añade o reemplaza una regla en tiempo de ejecución.

    Pensado para las pruebas contra SIIGO: cuando se capture el `Code` real que devuelve
    /v1/purchases ante una cuenta PUC inactiva, se puede fijar aquí y verificar el
    comportamiento completo antes de escribir la fila definitiva en la tabla de arriba.
    """
    _REGLAS_POR_CODIGO[code.strip().lower()] = _Regla(
        error_class=error_class,
        recommended_action=recommended_action,
        hint=hint,
        auto_retryable=auto_retryable,
    )


def known_error_codes() -> list:
    """Códigos catalogados. Útil para diagnóstico y para la documentación de la API."""
    return sorted(_REGLAS_POR_CODIGO)


def extract_siigo_codes(detail: Any) -> list:
    """Saca los códigos de error del cuerpo que devuelve siigo-service.

    Tolera las tres formas en que puede llegar —lista bajo `siigo_error_codes`, lista de
    objetos `Errors` con su `Code`, o nada— porque el cuerpo cambia según dónde se produjo el
    fallo, y un `KeyError` aquí convertiría un error clasificable en uno desconocido.
    """
    if not isinstance(detail, dict):
        return []
    codigos = detail.get("siigo_error_codes")
    if isinstance(codigos, list):
        return [c for c in codigos if c]
    errores = detail.get("Errors") or detail.get("errors")
    if isinstance(errores, list):
        return [e.get("Code") for e in errores if isinstance(e, dict) and e.get("Code")]
    return []
