from app.domain.exceptions.base import EntityNotFoundException
from app.domain.ports.repositories import DocumentRepositoryPort
from app.domain.value_objects.document_status import DocumentStatus


class CausarDocumentUseCase:
    """Procesado (100) → Causado (200), tras calcular la contabilización.

    Esta transición faltaba: el documento nacía en Procesado y los únicos casos de uso que
    escribían estado exigían Causado o Aprobado, así que nada podía salir de 100 y el resto
    de la máquina de estados quedaba inalcanzable. «Calcular contabilización» asignaba las
    cuentas y respondía OK, pero el documento no se movía de la pestaña.

    Es idempotente sobre un documento ya causado: el contador puede recalcular dos veces, o
    hacerlo sobre una selección donde alguno ya pasó, y eso no es un error que deba
    interrumpir el lote. En cambio no acepta un documento Aprobado o Contabilizado: causar
    no es la operación para deshacer una aprobación —para eso está `unapprove`— y degradarlo
    en silencio revertiría trabajo que el contador ya confirmó.
    """

    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_id: int):
        # La guarda solo necesita el estado, no la entidad: leerla entera aquí y otra vez
        # dentro de `update_status` era leer dos veces la misma fila para escribir un entero.
        estado = self.document_repo.get_status(document_id)
        if estado is None:
            raise EntityNotFoundException("Document", str(document_id))
        if estado == DocumentStatus.CAUSADO:
            return self.document_repo.get_by_id(document_id)
        if estado != DocumentStatus.PROCESADO:
            raise ValueError(
                "Document must be in 'Procesado' status (100) to be caused; "
                f"current status is {estado}"
            )
        return self.document_repo.update_status(document_id, DocumentStatus.CAUSADO)


class BulkCausarDocumentsUseCase:
    """Procesado (100) → Causado (200) para una selección completa, en una sola operación.

    Existe porque la pantalla de causación mueve el lote entero: el contador selecciona los
    documentos de un mes, calcula la contabilización y los pasa a Causado. Hacerlo documento
    por documento —una petición HTTP y una transacción por cada uno— es lo que hacía que la
    transición tardara minutos con una selección grande.

    Mantiene exactamente las mismas reglas que `CausarDocumentUseCase`, y las aplica dentro
    del UPDATE en vez de en una lectura previa: un documento ya Causado se cuenta como
    idempotente, uno Aprobado o Contabilizado se rechaza —causar no deshace una aprobación—,
    y uno inexistente se reporta como tal. Ningún documento inválido interrumpe el lote: la
    respuesta detalla qué pasó con cada id.
    """

    #: Únicos estados desde los que un lote puede avanzar a Causado. Retroceder desde
    #: Aprobado es `unapprove`, y deliberadamente no se admite aquí: un lote no debe poder
    #: revertir en masa un trabajo que el contador ya confirmó.
    ESTADOS_ORIGEN = frozenset({DocumentStatus.PROCESADO})

    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_ids: list[int]) -> dict:
        # Se deduplican conservando el orden de llegada: la selección de la interfaz puede
        # repetir un id (selección por páginas más selección explícita) y el informe debe
        # mencionar cada documento una sola vez.
        vistos: set[int] = set()
        unicos = [i for i in document_ids if not (i in vistos or vistos.add(i))]
        return self.document_repo.bulk_update_status(
            unicos, DocumentStatus.CAUSADO, self.ESTADOS_ORIGEN
        )


class ApproveDocumentUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    #: Estado exigido para aprobar. Se expone para que el caso de uso masivo aplique la
    #: misma regla sin duplicar el número.
    ESTADOS_ORIGEN = frozenset({DocumentStatus.CAUSADO})

    def execute(self, document_id: int):
        estado = self.document_repo.get_status(document_id)
        if estado is None:
            raise EntityNotFoundException("Document", str(document_id))
        if estado != DocumentStatus.CAUSADO:
            raise ValueError("Document must be in 'Causado' status (200) to approve")
        return self.document_repo.update_status(document_id, DocumentStatus.APROBADO)


class BulkApproveDocumentsUseCase:
    """Causado (200) → Aprobado (300) para una selección completa, en una sola operación.

    Misma razón y mismas garantías que `BulkCausarDocumentsUseCase`: la guarda de estado va
    dentro del UPDATE, un documento ya Aprobado es idempotente y ninguno inválido corta el
    lote.
    """

    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_ids: list[int]) -> dict:
        vistos: set[int] = set()
        unicos = [i for i in document_ids if not (i in vistos or vistos.add(i))]
        return self.document_repo.bulk_update_status(
            unicos, DocumentStatus.APROBADO, ApproveDocumentUseCase.ESTADOS_ORIGEN
        )


class UnapproveDocumentUseCase:
    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    ESTADOS_ORIGEN = frozenset({DocumentStatus.APROBADO})

    def execute(self, document_id: int):
        estado = self.document_repo.get_status(document_id)
        if estado is None:
            raise EntityNotFoundException("Document", str(document_id))
        if estado != DocumentStatus.APROBADO:
            raise ValueError("Document must be in 'Aprobado' status (300) to unapprove")
        return self.document_repo.update_status(document_id, DocumentStatus.CAUSADO)


class BulkUnapproveDocumentsUseCase:
    """Aprobado (300) → Causado (200) para una selección completa.

    El destino coincide con el de `BulkCausarDocumentsUseCase` pero el origen es el opuesto,
    y por eso son dos casos de uso y no uno con una lista de estados: avanzar desde Procesado
    y retroceder desde Aprobado son operaciones distintas que el contador pide con botones
    distintos. Fundirlas haría que «causar el lote» pudiera cancelar aprobaciones sin que
    nadie lo pidiera.
    """

    def __init__(self, document_repo: DocumentRepositoryPort):
        self.document_repo = document_repo

    def execute(self, document_ids: list[int]) -> dict:
        vistos: set[int] = set()
        unicos = [i for i in document_ids if not (i in vistos or vistos.add(i))]
        return self.document_repo.bulk_update_status(
            unicos, DocumentStatus.CAUSADO, UnapproveDocumentUseCase.ESTADOS_ORIGEN
        )
