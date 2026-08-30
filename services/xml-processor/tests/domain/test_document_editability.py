"""RF-01 — En qué estados se puede ajustar la imputación contable del documento.

Bug de origen: la interfaz solo permitía editar la cuenta PUC de una línea en estado
Procesado, cuando el requisito cubre también Causado. Y el servidor no comprobaba el estado
en absoluto: la API aceptaba cambiar las cuentas de un documento **Aprobado**, es decir,
alterar la imputación de la que el contador ya se había hecho responsable, sin cambio de
estado ni rastro alguno.

La regla vive aquí, en el dominio, y no repartida por los routers y los componentes Vue,
porque es una sola: la comparten la cuenta PUC (RF-01), el tipo de pago, el centro de costo
(RF-07) y las retenciones.
"""

from app.domain.value_objects.document_status import DocumentStatus


class TestDocumentEditability:
    def test_procesado_is_editable(self):
        assert DocumentStatus.is_editable(DocumentStatus.PROCESADO)

    def test_causado_is_editable(self):
        """El caso que faltaba: causado es cuando el contador revisa y corrige."""
        assert DocumentStatus.is_editable(DocumentStatus.CAUSADO)

    def test_aprobado_is_not_editable(self):
        """Aprobar es asumir la responsabilidad de la imputación: se congela."""
        assert not DocumentStatus.is_editable(DocumentStatus.APROBADO)

    def test_contabilizada_is_not_editable(self):
        assert not DocumentStatus.is_editable(DocumentStatus.CONTABILIZADA)

    def test_error_is_not_editable(self):
        """Un documento que no se pudo procesar no tiene imputación que ajustar."""
        assert not DocumentStatus.is_editable(DocumentStatus.ERROR)

    def test_accepts_the_status_as_text(self):
        """El estado llega como texto desde algunos orígenes; no debe abrir ni cerrar de más."""
        assert DocumentStatus.is_editable("200")
        assert not DocumentStatus.is_editable("300")

    def test_rejects_a_status_that_is_not_a_number(self):
        assert not DocumentStatus.is_editable(None)
        assert not DocumentStatus.is_editable("causado")

    def test_the_editable_set_is_exactly_procesado_and_causado(self):
        assert {
            DocumentStatus.PROCESADO,
            DocumentStatus.CAUSADO,
        } == DocumentStatus.EDITABLE
