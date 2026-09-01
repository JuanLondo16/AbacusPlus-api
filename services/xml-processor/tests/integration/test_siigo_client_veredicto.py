"""RF-05: de la respuesta de siigo-service al veredicto sobre el reintento.

La pregunta que responden estas pruebas es una sola, y es la que sostiene toda la seguridad
contable del requisito: **¿consta que SIIGO no creó la factura?** Solo cuando la respuesta es
un sí rotundo puede el documento volver a enviarse.

La responsabilidad está ahora repartida en dos piezas, y por eso se prueban juntas:

- el **cliente** extrae la evidencia —código HTTP, códigos de error de SIIGO, si hubo
  respuesta— sin interpretarla;
- el **clasificador** la interpreta, en un único sitio del sistema.

Antes esa decisión se tomaba en dos capas con criterios que discrepaban —una consideraba
seguro reenviar tras un 500 y la otra no—, y cuál ganaba dependía de por dónde hubiera
entrado el error. La mitad de estas pruebas existen para que esa discrepancia no vuelva.
"""

import httpx
import pytest
from app.domain.services.siigo_error_classifier import default_classifier
from app.domain.value_objects.accounting_error import (
    ErrorClass,
    RecommendedAction,
    is_safe_to_resend,
)
from app.infrastructure.clients.siigo_client import SiigoServiceClient


def _resp(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "http://x"))


def _veredicto(status, body):
    """Recorre el camino completo: respuesta HTTP → evidencia → clasificación → veredicto.

    Se prueba de extremo a extremo y no por piezas porque lo que importa no es que cada una
    haga su parte, sino que la conclusión final sea la correcta. Un fallo en la costura entre
    las dos es exactamente el defecto que estas pruebas deben atrapar.
    """
    resultado = SiigoServiceClient._failure_from_response(_resp(status, body))
    clasificacion = default_classifier.classify(
        status_code=resultado.status_code,
        siigo_codes=resultado.siigo_codes,
        message=resultado.error or "",
        no_response=resultado.no_response,
    )
    return clasificacion, is_safe_to_resend(clasificacion.recommended_action)


# ── Lo que NO consta: nunca se reenvía sin verificar ───────────────────────────


@pytest.mark.parametrize("status", [500, 502, 504])
def test_los_5xx_nunca_se_asumen_seguros(status):
    """Un 5xx no dice en qué momento falló SIIGO.

    Puede significar «no llegué a procesarlo» o «lo creé y fallé al responder». Como
    /v1/purchases no admite `Idempotency-Key`, tratarlo como seguro y reenviar crea un
    segundo asiento contable real en la contabilidad del cliente.
    """
    clasificacion, seguro = _veredicto(status, {"detail": "Internal Server Error"})

    assert seguro is False
    assert clasificacion.error_class == ErrorClass.UNCERTAIN
    assert clasificacion.recommended_action == RecommendedAction.RECONCILE


def test_un_502_con_veredicto_de_no_creacion_sigue_sin_ser_seguro():
    """Regresión del defecto más caro que tenía RF-05.

    `siigo_did_not_create` devolvía True para todo el rango 400–599, así que este caso
    —«SIIGO aceptó pero no devolvió id»— salía marcado como seguro para reenviar. Es
    justamente el caso en el que la factura sí puede existir.
    """
    clasificacion, seguro = _veredicto(
        502,
        {
            "detail": {
                "message": "SIIGO no devolvió el identificador",
                "siigo_did_not_create": False,
                "duplicate": False,
            }
        },
    )

    assert seguro is False
    assert clasificacion.recommended_action == RecommendedAction.RECONCILE


def test_el_duplicado_nunca_es_reenviable():
    """Si SIIGO dice que el comprobante ya existe, reenviarlo es crear el segundo."""
    clasificacion, seguro = _veredicto(
        409,
        {
            "detail": {
                "message": "duplicated_document",
                "siigo_error_codes": ["duplicated_document"],
                "duplicate": True,
                "siigo_did_not_create": True,
            }
        },
    )

    assert seguro is False
    assert clasificacion.error_class == ErrorClass.DUPLICATE
    assert clasificacion.recommended_action == RecommendedAction.RECONCILE


# ── Lo que sí consta: se reenvía, y la acción dice cómo ────────────────────────


@pytest.mark.parametrize(
    "status,clase,accion",
    [
        (400, ErrorClass.CORRECTABLE, RecommendedAction.EDIT_AND_RETRY),
        (404, ErrorClass.CORRECTABLE, RecommendedAction.EDIT_AND_RETRY),
        (422, ErrorClass.CORRECTABLE, RecommendedAction.EDIT_AND_RETRY),
        (401, ErrorClass.CONFIG, RecommendedAction.FIX_CONFIGURATION),
        (403, ErrorClass.CONFIG, RecommendedAction.FIX_CONFIGURATION),
        (429, ErrorClass.RATE_LIMIT, RecommendedAction.RETRY),
        (503, ErrorClass.TRANSIENT, RecommendedAction.RETRY),
    ],
)
def test_los_rechazos_confirmados_son_reenviables(status, clase, accion):
    """SIIGO rechazó la petición antes de tocar la contabilidad: reenviar es seguro.

    Y cada código determina QUÉ puede hacer el usuario. Ésa es la parte que sustituye a los
    estados que RF-05 prohíbe crear: el documento siempre queda en Error, y lo que cambia
    entre un caso y otro es la acción recomendada.
    """
    clasificacion, seguro = _veredicto(status, {"detail": {"message": "x"}})

    assert seguro is True
    assert clasificacion.error_class == clase
    assert clasificacion.recommended_action == accion


def test_un_codigo_de_siigo_manda_sobre_el_codigo_http():
    """El código de error de SIIGO es más específico que el HTTP, y gana.

    Un 400 genérico se clasifica como corregible; el mismo 400 con `requests_limit` es un
    problema de cupo que se resuelve esperando, no corrigiendo nada.
    """
    clasificacion, seguro = _veredicto(
        400, {"detail": {"message": "límite", "siigo_error_codes": ["requests_limit"]}}
    )

    assert seguro is True
    assert clasificacion.error_class == ErrorClass.RATE_LIMIT
    assert clasificacion.auto_retryable is True


def test_un_codigo_desconocido_no_degrada_a_uno_conocido():
    """Con varios errores a la vez se toma el primero CATALOGADO, no el primero a secas.

    Si no, un código nuevo sin catalogar eclipsaría a uno que sí sabemos interpretar y
    degradaría la clasificación a desconocida sin necesidad.
    """
    clasificacion, _ = _veredicto(
        400,
        {
            "detail": {
                "message": "x",
                "siigo_error_codes": ["algo_que_no_conocemos", "invalid_reference"],
            }
        },
    )

    assert clasificacion.error_class == ErrorClass.CORRECTABLE
    assert clasificacion.siigo_code == "invalid_reference"


# ── Ausencia total de respuesta ────────────────────────────────────────────────


def test_sin_respuesta_no_se_sabe_nada():
    """Timeout o corte de red: la petición pudo llegar y crear la factura."""
    clasificacion = default_classifier.classify(
        message="SIIGO no respondió a tiempo", no_response=True
    )

    assert is_safe_to_resend(clasificacion.recommended_action) is False
    assert clasificacion.error_class == ErrorClass.UNCERTAIN


def test_la_validacion_local_es_la_unica_certeza_absoluta():
    """Si la petición no llegó a salir de Abacus, consta que SIIGO no creó nada."""
    clasificacion = default_classifier.classify(
        message="El documento no tiene NIT del proveedor", local_validation=True
    )

    assert is_safe_to_resend(clasificacion.recommended_action) is True
    assert clasificacion.recommended_action == RecommendedAction.EDIT_AND_RETRY


def test_el_mensaje_de_siigo_se_conserva_intacto():
    """El contador necesita saber qué hacer; el soporte, qué dijo SIIGO exactamente."""
    clasificacion, _ = _veredicto(
        400,
        {
            "detail": {
                "message": "La cuenta 510505 no existe",
                "siigo_error_codes": ["invalid_reference"],
            }
        },
    )

    assert "La cuenta 510505 no existe" in clasificacion.message
    # Y además una pista accionable derivada del texto, que es lo que convierte
    # «invalid_reference» en algo que un contador puede arreglar.
    assert "cuenta contable" in clasificacion.message
