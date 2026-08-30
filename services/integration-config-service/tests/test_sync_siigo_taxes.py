"""El catálogo de impuestos debe conservar el identificador que usa SIIGO.

Un impuesto no se le nombra a SIIGO al contabilizar: se le manda su `id`, dentro de
`retentions` o de `items[].taxes`. Si la sincronización descarta ese id, la tabla lo suple
con su propia secuencia y esas claves —que solo existen aquí— acaban viajando a SIIGO, que
responde `The id doesn't exist`. Ocurrió en producción con `ReteIVA 15%`, guardado como 15
cuando en SIIGO es 10608.

La sincronización de tipos de pago sí lo conservaba desde el principio; la de impuestos era
la excepción, y por eso el tipo de pago funcionaba y el impuesto no.
"""

from app.application.use_cases.sync_siigo_taxes import SyncSiigoTaxesUseCase

_RESPUESTA_SIIGO = {
    "id": 10608,
    "name": "ReteIVA 15%",
    "type": "ReteIVA",
    "percentage": 15.0,
    "active": True,
}


class TestElIdDeSiigoSeConserva:
    def test_el_id_viaja_en_el_mapeo(self):
        assert SyncSiigoTaxesUseCase._map_item(_RESPUESTA_SIIGO)["id"] == 10608

    def test_no_se_sustituye_por_el_nombre_ni_por_el_porcentaje(self):
        mapeado = SyncSiigoTaxesUseCase._map_item(_RESPUESTA_SIIGO)

        assert mapeado["id"] != 15, "15 es el porcentaje, no el identificador"
        assert mapeado["name"] == "ReteIVA 15%"
        assert mapeado["percentage"] == 15.0

    def test_una_respuesta_sin_id_no_lo_inventa(self):
        """Sin id no se fabrica uno: es preferible que el repositorio lo trate aparte."""
        sin_id = {k: v for k, v in _RESPUESTA_SIIGO.items() if k != "id"}

        assert SyncSiigoTaxesUseCase._map_item(sin_id)["id"] is None
