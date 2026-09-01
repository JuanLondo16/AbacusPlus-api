class DomainException(Exception):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class NoChartOfAccountsError(DomainException):
    """RF-08: no hay Plan Único de Cuentas cargado, así que no se sugieren cuentas.

    El alcance lo define como regla de negocio crítica: sin PUC el modelo no debe inventar
    ni sugerir cuentas de un PUC colombiano genérico, sino detener el proceso con este
    mensaje textual.
    """

    MESSAGE = "No tienes un plan único de cuenta"

    def __init__(self, message: str = MESSAGE):
        super().__init__(message=message, code="NO_CHART_OF_ACCOUNTS")


class NoRetentionCatalogError(DomainException):
    """RF-08: no hay catálogo de retenciones, así que no se pueden sugerir retenciones.

    Mismo principio que la regla del plan de cuentas: sin catálogo sincronizado el modelo
    tendría que inventar retenciones y porcentajes, así que el proceso se detiene. La
    tarifa siempre proviene del catálogo, nunca del modelo.

    Se llamó `NoTaxCatalogError` hasta que el split del 2026-08-31 separó impuestos
    (`integration_taxes`) de retenciones (`integration_retentions`): el chequeo siempre
    fue sobre el catálogo de retenciones, pero el nombre y el mensaje seguían hablando de
    impuestos, así que quien lo veía revisaba y sincronizaba la tabla equivocada.
    """

    MESSAGE = "No tienes un catálogo de retenciones sincronizado"

    def __init__(self, message: str = MESSAGE):
        super().__init__(message=message, code="NO_RETENTION_CATALOG")
