"""Qué retenciones puede practicar SIIGO en una factura de compra.

Existe para que la interfaz y el envío decidan sobre lo MISMO. Estaban decidiendo distinto:
el selector ofrecía todo el catálogo sincronizado y el envío descartaba lo que la API rechaza,
así que el contador registraba una Retefuente, veía el total a pagar descontado en Abacus y
en SIIGO quedaba el importe íntegro. Dos pantallas, dos verdades y una diferencia silenciosa
sobre dinero de un tercero.

La lista sale de la documentación de `POST /v1/purchases` —«Array con los id de los impuestos
tipo ReteICA, ReteIVA»— y está confirmada contra el ambiente real: son las dos únicas que
SIIGO ha practicado. El resto fue rechazado en los dos sitios posibles del cuerpo:

    retentions      → invalid_array: "The array id has invalid values"
    items[0].taxes  → invalid_array: "The array taxes has invalid values"

Los tipos disponibles los fija la configuración del comprobante, no la API: «De acuerdo a la
configuración del comprobante en el menú Configuración > Transacciones > Facturas, sección
Datos tributarios, puedes utilizar los siguientes tipos de retenciones». El comprobante de
compra del cliente declara `reteiva: true` y `reteica: true`, que es exactamente esta lista.

Si mañana se habilita la Autorretención en esa configuración, se añade aquí y las dos capas
cambian a la vez. Ése es el motivo de que la constante viva sola en un módulo de dominio y no
dentro del caso de uso.
"""

#: Tipos —en minúsculas, como se comparan— que SIIGO admite en `retentions` de una compra.
#:
#: LA AUTORRETENCIÓN NO SE PUEDE HABILITAR AQUÍ. NO ES UNA CONFIGURACIÓN PENDIENTE.
#:
#: Una versión anterior de este módulo dejaba escritas tres instrucciones para activarla,
#: la segunda de las cuales era «comprobar que `GET /v1/document-types?type=FC` devuelve la
#: bandera nueva». Esa bandera no va a aparecer nunca, y seguir esas instrucciones solo puede
#: gastar tiempo. El blueprint oficial lo dice sin ambigüedad:
#:
#:   · `DocumentTypeFC` —comprobante de COMPRA— declara `reteiva`, `reteica` y
#:     `consumption_tax`. No tiene ningún campo de autorretención.
#:   · `DocumentTypeFV` —comprobante de VENTA— sí declara `self_withholding` y
#:     `self_withholding_limit`.
#:
#: Y encaja con la figura tributaria: la autorretención de renta la practica una empresa sobre
#: SUS PROPIOS INGRESOS. En una factura de compra, que el proveedor sea autorretenedor
#: (código O-15) no significa que haya que aplicarle una autorretención; significa lo
#: contrario: que NO se le practica retención en la fuente, porque él se la practica a sí
#: mismo. Es una regla de supresión sobre el tercero, no una retención que enviar — y RF-08 ya
#: la aplica en `retention_validation.py`.
#:
#: La tabla descriptiva del PUT de compras sí menciona la Autorretención, y la del POST no.
#: Esa discrepancia es del propio blueprint; la estructura de `DocumentTypeFC` la resuelve.
TIPOS_DE_RETENCION_EN_COMPRAS: tuple = ("reteica", "reteiva")


def es_retencion_practicable(tipo) -> bool:
    """True si SIIGO puede practicar una retención de ese tipo en una factura de compra.

    Se normaliza el tipo porque el catálogo escribe la misma clase de varias formas
    —«ReteIVA», «reteiva»— y comparar la cadena literal dejaría fuera a la mitad.
    """
    return str(tipo or "").strip().lower() in TIPOS_DE_RETENCION_EN_COMPRAS


#: Tipos que viajan DENTRO de cada línea, en `items[].taxes`.
#:
#: SIIGO no publica una lista blanca para los ítems: publica una prohibición —«Si envías un
#: reteIVA o reteICA en los items de factura»— y un límite de tres impuestos por ítem. De los
#: siete tipos del enum `TaxType`, estos son los que quedan fuera de esa prohibición y son
#: impuestos en sentido estricto: se suman al valor de la operación en lugar de descontarse.
#:
#: El Impoconsumo está confirmado contra el ambiente real: la factura F78P21635 se contabilizó
#: con `Impoconsumo 8%` en sus dos líneas y SIIGO lo devolvió aplicado (5.844,44 y 362,96),
#: con el total intacto en 83.800. El IVA lleva funcionando desde el primer documento.
#:
#: AdValorem se incluye porque el enum lo declara y la prohibición no lo alcanza, pero NO se
#: ha probado: no hay ninguno en el catálogo de la empresa. Si algún día aparece y SIIGO lo
#: rechaza, se retira de aquí y nada más cambia.
TIPOS_DE_IMPUESTO_DE_LINEA: tuple = ("iva", "impoconsumo", "advalorem")


def es_impuesto_de_linea(tipo) -> bool:
    """True si el impuesto se asigna a una línea y suma al valor de la operación.

    Es la contraparte de `es_retencion_practicable`: juntas reparten el catálogo entre los dos
    sitios que SIIGO expone, sin que ningún tipo pueda acabar en el equivocado. Un impuesto
    puesto donde va una retención se resta en lugar de sumarse, y esa fue exactamente la
    confusión que descuadró cuatro documentos con el impuesto al consumo.
    """
    return str(tipo or "").strip().lower() in TIPOS_DE_IMPUESTO_DE_LINEA
