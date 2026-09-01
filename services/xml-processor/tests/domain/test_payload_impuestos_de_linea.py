"""El envío a SIIGO debe llevar todos los impuestos de la línea, no solo uno.

Con la lista completa ya guardada en `document_details.taxes`, falta que el cuerpo de
`POST /v1/purchases` la use. Son dos cosas distintas y las dos importan:

1. **`items[].taxes`** — los identificadores que SIIGO va a aplicar.
2. **El total esperado** — SIIGO valida que `payments[].value` coincida con lo que él calcula
   a partir de los ítems. Si anticipamos el total contando solo un impuesto por línea, el
   cálculo no cuadra y responde `invalid_total_payments`.

La composición de la lista obedece las reglas de `siigo_item_taxes`: tope de tres, un solo
impuesto por tipo, sin retenciones y sin IVA junto a AdValorem.
"""

from app.domain.services.payload_line_taxes import impuestos_de_la_linea


class _Linea:
    """Una línea de detalle, con solo lo que esta función necesita."""

    def __init__(self, taxes=None, tax_id=None, tax_type="0"):
        self.taxes = taxes
        self.tax_id = tax_id
        self.tax_type = tax_type


#: Porcentaje → id del catálogo, tal como lo devuelve `indice_por_porcentaje`.
CATALOGO = {19.0: 101, 8.0: 10609, 4.0: 777, 5.0: 202}

#: id → tipo, para aplicar las reglas de composición de SIIGO.
TIPOS = {101: "IVA", 10609: "Impoconsumo", 777: "Impoconsumo", 202: "IVA"}


class TestLineaConVariosImpuestos:
    def test_envia_los_dos_identificadores(self):
        """El caso de las ocho facturas de telecomunicaciones: IVA 19 % e INC 4 %."""
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25, "tax_id": 101},
                {"esquema": "04", "porcentaje": 4.0, "valor": 499.0, "tax_id": 777},
            ]
        )
        ids, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [101, 777]

    def test_el_importe_esperado_suma_los_dos(self):
        """Con solo el IVA, el total anticipado se quedaba $499 corto por línea."""
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25, "tax_id": 101},
                {"esquema": "04", "porcentaje": 4.0, "valor": 499.0, "tax_id": 777},
            ]
        )
        _, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert round(impuesto, 2) == 2869.25


class TestLineaConUnSoloImpuesto:
    def test_se_comporta_como_antes(self):
        """No se altera el caso mayoritario: una línea con IVA y nada más."""
        linea = _Linea(
            taxes=[{"esquema": "01", "porcentaje": 19.0, "valor": 1195.88, "tax_id": 101}]
        )
        ids, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [101]
        assert round(impuesto, 2) == 1195.88

    def test_el_impoconsumo_viaja_como_impuesto_de_linea(self):
        """La factura F78P21635, contabilizada con `tax_ids: [10609]`."""
        linea = _Linea(
            taxes=[{"esquema": "04", "porcentaje": 8.0, "valor": 5844.44, "tax_id": 10609}]
        )
        ids, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [10609]
        assert round(impuesto, 2) == 5844.44


class TestLoQueEligeElContadorManda:
    def test_un_tax_id_puesto_a_mano_prevalece(self):
        """Si el contador fijó el impuesto de la línea, se respeta sobre lo deducido."""
        linea = _Linea(taxes=None, tax_id=202, tax_type="5.00")
        ids, _, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [202]


class TestCompatibilidadConDocumentosAntiguos:
    def test_una_linea_sin_lista_usa_el_impuesto_principal(self):
        """Los documentos guardados antes de esta corrección no tienen `taxes`.

        Deben seguir contabilizándose exactamente igual que antes, deduciendo el impuesto de
        `tax_type`. Una corrección que impidiera contabilizar el histórico sería peor que el
        defecto que arregla.
        """
        linea = _Linea(taxes=None, tax_type="19.00")
        ids, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS, base=1000.0)
        assert ids == [101]
        assert round(impuesto, 2) == 190.0

    def test_una_linea_antigua_exenta_no_lleva_impuesto(self):
        linea = _Linea(taxes=None, tax_type="0")
        ids, impuesto, _ = impuestos_de_la_linea(linea, CATALOGO, TIPOS, base=1000.0)
        assert ids == []
        assert impuesto == 0.0


class TestSeAplicanLasReglasDeSiigo:
    def test_no_viajan_dos_impuestos_del_mismo_tipo(self):
        """Dos IVA en la misma línea son un rechazo del documento entero."""
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 100.0, "tax_id": 101},
                {"esquema": "01", "porcentaje": 5.0, "valor": 50.0, "tax_id": 202},
            ]
        )
        ids, _, avisos = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [101]
        assert avisos

    def test_un_impuesto_sin_enlace_no_rompe_la_linea(self):
        """Si el catálogo no tiene ese porcentaje, la línea viaja con lo que sí se pudo
        enlazar, y el descarte queda avisado."""
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 100.0, "tax_id": 101},
                {"esquema": "99", "porcentaje": 7.5, "valor": 30.0, "tax_id": None},
            ]
        )
        ids, impuesto, avisos = impuestos_de_la_linea(linea, CATALOGO, TIPOS)
        assert ids == [101]
        assert avisos
        # El importe cuenta SOLO lo que viaja. El impuesto sin enlazar existe en la factura,
        # pero como no se le manda a SIIGO, SIIGO no lo va a calcular: incluirlo aquí dejaría
        # la línea de ajuste corta por esa misma cantidad y el total contabilizado por debajo
        # del facturado. Quien aporta ese importe es el ajuste, no esta cifra.
        assert round(impuesto, 2) == 100.0


class TestElImporteAnticipaLoQueSiigoCalculara:
    """Regresión de BEC520526814: el total contabilizado salió 499 pesos corto.

    La línea declaraba IVA 19 % e INC 4 %. En el catálogo no hay ningún Impoconsumo del 4 %,
    pero sí un «Retefuente 4 %», así que el INC enlazaba con una retención. Una retención no
    puede viajar dentro de un ítem, de modo que se descartaba al componer — correctamente — y
    sus 499 pesos se quedaban contados en el importe sin que nadie los enviara. SIIGO
    registró 133.350 donde la DIAN decía 133.849.
    """

    #: El catálogo real del cliente: el 4 % que existe es una retención, no un impoconsumo.
    CATALOGO_SIN_INC_4 = {19.0: 20921, 4.0: 10599}
    TIPOS_REALES = {20921: "IVA", 10599: "Retefuente"}

    def _linea_del_documento(self):
        return _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25, "tax_id": 20921},
                {"esquema": "04", "porcentaje": 4.0, "valor": 499.0, "tax_id": 10599},
            ]
        )

    def test_no_enlaza_un_inc_con_una_retencion(self):
        ids, _, _ = impuestos_de_la_linea(
            self._linea_del_documento(), self.CATALOGO_SIN_INC_4, self.TIPOS_REALES
        )
        assert ids == [20921], "la retención no puede viajar como impuesto de la línea"

    def test_el_importe_no_cuenta_el_impuesto_descartado(self):
        """Lo que descuadraba el documento: 2370.25, no 2869.25."""
        _, impuesto, _ = impuestos_de_la_linea(
            self._linea_del_documento(), self.CATALOGO_SIN_INC_4, self.TIPOS_REALES
        )
        assert impuesto == 2370.25

    def test_el_aviso_nombra_el_problema_y_la_solucion(self):
        _, _, avisos = impuestos_de_la_linea(
            self._linea_del_documento(), self.CATALOGO_SIN_INC_4, self.TIPOS_REALES
        )
        assert any("retefuente" in a.lower() for a in avisos)
        assert any("impoconsumo" in a.lower() for a in avisos)

    def test_con_el_impoconsumo_bien_configurado_si_viaja(self):
        """El arreglo de datos completo: crear el Impoconsumo 4 % en SIIGO **y** soltar el
        enlace viejo.

        No basta con arreglar el catálogo. `taxes[].tax_id` manda sobre el índice, así que un
        documento que ya guardó el enlace equivocado lo sigue usando: hay que ponerlo a NULL
        para que se vuelva a resolver contra el catálogo corregido.
        """
        catalogo = {19.0: 20921, 4.0: 10615}
        tipos = {20921: "IVA", 10615: "Impoconsumo"}
        linea = _Linea(
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25, "tax_id": 20921},
                {"esquema": "04", "porcentaje": 4.0, "valor": 499.0, "tax_id": None},
            ]
        )
        ids, impuesto, _ = impuestos_de_la_linea(linea, catalogo, tipos)
        assert ids == [20921, 10615]
        assert impuesto == 2869.25

    def test_el_enlace_viejo_equivocado_se_sigue_rechazando(self):
        """Aunque el catálogo ya tenga el Impoconsumo 4 %, un `tax_id` rancio que apunta a la
        retención no puede colarse: el tipo lo delata."""
        catalogo = {19.0: 20921, 4.0: 10615}
        tipos = {20921: "IVA", 10615: "Impoconsumo", 10599: "Retefuente"}
        ids, impuesto, _ = impuestos_de_la_linea(self._linea_del_documento(), catalogo, tipos)
        assert ids == [20921]
        assert impuesto == 2370.25

    def test_un_esquema_desconocido_no_se_rechaza(self):
        """Permisivo ante lo que no está en el mapa: no se cambia lo que ya funcionaba."""
        linea = _Linea(
            taxes=[{"esquema": "35", "porcentaje": 19.0, "valor": 100.0, "tax_id": 20921}]
        )
        ids, impuesto, _ = impuestos_de_la_linea(linea, self.CATALOGO_SIN_INC_4, self.TIPOS_REALES)
        assert ids == [20921]
        assert impuesto == 100.0


class TestElImpuestoFijadoNoExcluyeALosDemas:
    """`document_details.tax_id` fija UNA preferencia, no una exclusión.

    Es una sola columna: no puede expresar dos impuestos. Tratarla como «esta línea viaja con
    este impuesto y con ninguno más» convertía esa limitación de la columna en una pérdida de
    datos de la factura — un renglón con IVA 19 % e INC 4 % enviaba solo el IVA aunque el
    catálogo tuviera los dos.

    Lo que sí fija es el orden: el elegido va primero, así que ante un descarte por las reglas
    de SIIGO es el que se conserva.
    """

    CATALOGO_MULTI = {19.0: 101, 4.0: 777}
    TIPOS_MULTI = {101: "IVA", 777: "Impoconsumo", 202: "IVA"}

    def _linea(self, tax_id):
        return _Linea(
            tax_id=tax_id,
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 2370.25, "tax_id": 101},
                {"esquema": "04", "porcentaje": 4.0, "valor": 499.0, "tax_id": 777},
            ],
        )

    def test_viajan_los_dos_impuestos(self):
        ids, importe, _ = impuestos_de_la_linea(
            self._linea(101), self.CATALOGO_MULTI, self.TIPOS_MULTI
        )
        assert ids == [101, 777], "el INC no puede quedarse fuera por haber fijado el IVA"
        assert importe == 2869.25

    def test_el_fijado_va_primero(self):
        ids, _, _ = impuestos_de_la_linea(self._linea(777), self.CATALOGO_MULTI, self.TIPOS_MULTI)
        assert ids[0] == 777

    def test_ante_un_descarte_se_conserva_el_fijado(self):
        """Dos IVA en la misma línea son un rechazo de SIIGO: sobrevive el elegido."""
        linea = _Linea(
            tax_id=202,
            taxes=[
                {"esquema": "01", "porcentaje": 19.0, "valor": 100.0, "tax_id": 101},
                {"esquema": "01", "porcentaje": 5.0, "valor": 50.0, "tax_id": 202},
            ],
        )
        ids, _, avisos = impuestos_de_la_linea(linea, self.CATALOGO_MULTI, self.TIPOS_MULTI)
        assert ids == [202]
        assert avisos

    def test_documento_antiguo_sin_desglose_no_cambia(self):
        """Sin lista de impuestos no hay nada que acompañar: comportamiento anterior intacto."""
        linea = _Linea(tax_id=101, taxes=None, tax_type="19.0")
        ids, importe, _ = impuestos_de_la_linea(
            linea, self.CATALOGO_MULTI, self.TIPOS_MULTI, base=1000.0
        )
        assert ids == [101]
        assert importe == 190.0

    def test_una_linea_sin_impuestos(self):
        linea = _Linea(tax_id=None, taxes=None, tax_type="0")
        ids, importe, _ = impuestos_de_la_linea(linea, self.CATALOGO_MULTI, self.TIPOS_MULTI)
        assert ids == []
        assert importe == 0.0
