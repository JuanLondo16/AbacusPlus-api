"""RF-05: de la clasificación interna a los dos botones que ve el contador.

Este archivo prueba la frontera. Por dentro el sistema distingue siete clases de error
—tiene que hacerlo: de esa distinción depende que no se dupliquen asientos contables—, y
hacia la pantalla solo cruzan dos booleanos.

Lo que se verifica aquí es que esa reducción no pierda la única garantía que importa:
**`can_retry` nunca puede ser True cuando no consta que SIIGO dejó de crear la factura.**
"""

import pytest
from app.domain.services.siigo_error_classifier import default_classifier
from app.domain.value_objects.accounting_error import (
    ErrorClass,
    RecommendedAction,
    can_edit,
    can_retry,
)


@pytest.mark.parametrize(
    "accion,editar,reintentar",
    [
        (RecommendedAction.EDIT_AND_RETRY, True, True),
        (RecommendedAction.RETRY, False, True),
        (RecommendedAction.FIX_CONFIGURATION, False, True),
        # Las dos únicas combinaciones en las que el reintento queda cerrado. Son las que
        # protegen la contabilidad del cliente.
        (RecommendedAction.RECONCILE, False, False),
        (RecommendedAction.MANUAL_REVIEW, False, False),
    ],
)
def test_cada_accion_se_reduce_a_dos_booleanos(accion, editar, reintentar):
    assert can_edit(accion) is editar
    assert can_retry(accion) is reintentar


def test_una_accion_desconocida_no_habilita_nada():
    """Si aparece un valor que no reconocemos, lo seguro es no ofrecer ninguna acción.

    Presumir que un fallo desconocido es inocuo es exactamente lo que crea duplicados.
    """
    assert can_edit("ALGO_NUEVO") is False
    assert can_retry("ALGO_NUEVO") is False
    assert can_edit("") is False
    assert can_retry("") is False


@pytest.mark.parametrize(
    "status,codigos,editar,reintentar",
    [
        # Datos contables rechazados: se corrigen y se reenvían.
        (400, ["invalid_reference"], True, True),
        (400, ["parameter_required"], True, True),
        (404, ["not_found"], True, True),
        (422, [], True, True),
        # Cupo y disponibilidad: se reintentan sin tocar nada.
        (429, ["requests_limit"], False, True),
        (503, ["service_unavailable"], False, True),
        # Credenciales: se arregla la integración, no el documento.
        (401, ["unauthorized"], False, True),
        # Desenlace desconocido: ni editar ni reintentar hasta verificar en SIIGO.
        (500, ["unhandled_error"], False, False),
        (502, [], False, False),
        (504, [], False, False),
        (408, ["request_timeout"], False, False),
        (409, ["duplicated_document"], False, False),
    ],
)
def test_del_error_de_siigo_a_las_capacidades(status, codigos, editar, reintentar):
    """El recorrido completo, que es el que de verdad se ejecuta en producción."""
    clasificacion = default_classifier.classify(
        status_code=status, siigo_codes=codigos, message="x"
    )

    assert can_edit(clasificacion.recommended_action) is editar
    assert can_retry(clasificacion.recommended_action) is reintentar


def test_ningun_fallo_incierto_habilita_el_reintento():
    """Invariante del sistema, comprobado sobre la clase y no sobre casos sueltos.

    Da igual qué código traiga o cómo llegue: si la clasificación acaba en `UNCERTAIN`, el
    reintento está cerrado. Esta prueba falla si alguien añade una regla que mapee un fallo
    incierto a una acción reenviable, que es el error más caro que se puede cometer en este
    módulo.
    """
    casos = [
        {"status_code": 500},
        {"status_code": 502},
        {"status_code": 504},
        {"status_code": 408},
        {"no_response": True},
        {"status_code": 200, "siigo_codes": [], "no_response": True},
    ]

    for caso in casos:
        clasificacion = default_classifier.classify(message="x", **caso)
        assert clasificacion.error_class == ErrorClass.UNCERTAIN
        assert can_retry(clasificacion.recommended_action) is False
        assert can_edit(clasificacion.recommended_action) is False


def test_la_validacion_local_habilita_editar_y_reintentar():
    """La petición no salió de Abacus, así que consta que SIIGO no creó nada."""
    clasificacion = default_classifier.classify(
        message="Falta el NIT del proveedor", local_validation=True
    )

    assert can_edit(clasificacion.recommended_action) is True
    assert can_retry(clasificacion.recommended_action) is True


def test_un_codigo_nuevo_se_puede_registrar_sin_tocar_otros_componentes():
    """La prueba de que la estructura es escalable, no solo de que está bien escrita.

    Añadir un error que SIIGO devuelva mañana debe ser una fila en la tabla de reglas. Si
    esta prueba deja de pasar, es que la clasificación volvió a estar repartida por varios
    sitios.
    """
    from app.domain.services.siigo_error_classifier import register_error_code

    register_error_code(
        "inactive_account",
        error_class=ErrorClass.CORRECTABLE,
        recommended_action=RecommendedAction.EDIT_AND_RETRY,
        hint="La cuenta contable está inactiva en SIIGO.",
    )

    clasificacion = default_classifier.classify(
        status_code=400, siigo_codes=["inactive_account"], message="cuenta inactiva"
    )

    assert can_edit(clasificacion.recommended_action) is True
    assert clasificacion.siigo_code == "inactive_account"
