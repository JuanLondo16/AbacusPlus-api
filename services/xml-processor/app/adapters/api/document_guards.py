"""Guardas de estado compartidas por los routers que modifican un documento.

Vive en un módulo propio y no dentro de un router porque la regla la aplican varios: la
cuenta PUC por línea (RF-01), las retenciones (RF-02), el tipo de pago, el centro de costo
(RF-07) y la ruta interna del llm-service. Tener una copia por router es exactamente lo que
hizo que la regla se escribiera de tres formas distintas y que las retenciones se quedaran
sin protección.

La regla en sí es del dominio (`DocumentStatus.is_editable_document`); aquí solo se traduce
a HTTP.
"""

from fastapi import HTTPException, status

from app.domain.value_objects.document_status import DocumentStatus


def require_editable(doc) -> None:
    """Impide alterar la imputación de un documento ya aprobado o contabilizado.

    Aprobar es el acto por el que el contador se hace responsable de lo imputado; permitir
    cambiarlo después lo alteraría sin dejar rastro ni exigir una nueva aprobación. Para
    volver a editar hay que cancelar la aprobación (`PATCH /documents/{id}` con
    `status: 200`), que devuelve el documento a Causado de forma explícita.

    **RF-05 añade una excepción**, y es la que hace posible «Editar y reintentar»: un
    documento que SIIGO rechazó por un dato contable —cuenta PUC inexistente o inactiva,
    centro de costo, impuesto o retención inválidos— queda en `Error` y **sí** puede
    corregirse, porque corregirlo es justamente la acción que el sistema le pide al contador.
    Sin esa excepción el documento quedaría atrapado en un error que nadie puede arreglar.

    La excepción está acotada en el dominio: solo alcanza a los errores clasificados como
    `EDITAR_Y_REINTENTAR`. Un fallo de red o un desenlace incierto no se arreglan editando, y
    abrir la edición ahí invitaría a tocar un documento que quizá ya está en SIIGO.
    """
    if not DocumentStatus.is_editable_document(doc):
        nombre = DocumentStatus.NAMES.get(doc.status, doc.status)
        if doc.status == DocumentStatus.ERROR:
            detalle = (
                "El documento está en 'Error' pero su fallo no se corrige editando la "
                "causación. Revise la acción recomendada del documento."
            )
        else:
            detalle = (
                f"El documento está en estado '{nombre}' y su imputación no puede "
                "modificarse. Cancele la aprobación para volver a editarlo."
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
