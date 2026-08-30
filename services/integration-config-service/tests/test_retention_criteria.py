"""RF-08 · Criterios del contador como datos por empresa.

Lo que se fija aquí es la razón de que existan como tabla y no como constante: que cada
cliente tenga los suyos, que se puedan cambiar sin desplegar, y que re-aprovisionar a un
cliente no pise el trabajo de su contador.
"""

import pytest
from app.application.dto.retention_criteria import (
    RetentionCriteriaReplaceRequest,
    RetentionCriterionItem,
)
from app.application.use_cases.manage_retention_criteria import ManageRetentionCriteriaUseCase
from app.domain.services.retention_criteria_seed import CRITERIOS_POR_DEFECTO
from app.infrastructure.config.database import Base
from app.infrastructure.persistence.models.retention_criteria import (
    RetentionCriterion,  # noqa: F401
)
from app.infrastructure.persistence.repositories.retention_criteria_repository import (
    RetentionCriteriaRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[RetentionCriterion.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield RetentionCriteriaRepository(session)
    finally:
        session.close()


def _criterio(tema="reteica", criterio="Por el municipio.", activo=True):
    return {
        "tema": tema,
        "pregunta": "¿Cómo se determina?",
        "criterio": criterio,
        "activo": activo,
        "fuente": "prueba",
    }


class TestSemilla:
    def test_un_tenant_nuevo_arranca_con_criterios(self, repo):
        """Sin semilla, la sugerencia perdería su fuente orientativa desde el primer día."""
        cargados = repo.seed_if_empty(CRITERIOS_POR_DEFECTO)

        assert cargados == len(CRITERIOS_POR_DEFECTO)
        assert repo.count() == len(CRITERIOS_POR_DEFECTO)

    def test_reaprovisionar_no_pisa_el_trabajo_del_contador(self, repo):
        """El seed es no destructivo: si ya hay criterios, no se toca nada.

        Es la misma garantía que el auto-seed de tarifas de ReteFuente. Un cliente que lleva
        meses afinando sus criterios no puede perderlos porque alguien vuelva a aprovisionar.
        """
        repo.replace_all([_criterio(criterio="Criterio afinado por el contador")])

        cargados = repo.seed_if_empty(CRITERIOS_POR_DEFECTO)

        assert cargados == 0
        assert repo.list_all()[0].criterio == "Criterio afinado por el contador"

    def test_la_semilla_cubre_las_tres_retenciones_y_el_proceso(self):
        temas = {c["tema"] for c in CRITERIOS_POR_DEFECTO}

        assert {"retefuente", "reteica", "reteiva", "proceso"} <= temas


class TestEdicionSinDesplegar:
    def test_reemplazar_deja_vigentes_los_nuevos(self, repo):
        """Cambiar un criterio no exige tocar código ni reiniciar nada."""
        use_case = ManageRetentionCriteriaUseCase(repo)
        repo.seed_if_empty(CRITERIOS_POR_DEFECTO)

        respuesta = use_case.replace(
            RetentionCriteriaReplaceRequest(
                criterios=[
                    RetentionCriterionItem(
                        tema="reteiva",
                        pregunta="¿Qué tarifa aplica?",
                        criterio="El 15% sobre el IVA, confirmado en agosto.",
                    )
                ]
            )
        )

        assert respuesta.total == 1
        assert use_case.get().criterios[0].criterio.startswith("El 15%")

    def test_un_criterio_desactivado_no_llega_al_modelo(self, repo):
        """Permite retirar un criterio sin borrar el rastro de que existió."""
        repo.replace_all([_criterio(activo=True), _criterio(tema="proceso", activo=False)])
        use_case = ManageRetentionCriteriaUseCase(repo)

        assert use_case.get().total == 1
        assert use_case.get(only_active=False).total == 2

    def test_el_orden_es_estable(self, repo):
        """La misma factura debe producir siempre la misma sugerencia.

        Un orden variable de los criterios cambia el prompt y, con él, la respuesta: en una
        decisión tributaria eso es inaceptable.
        """
        repo.replace_all([_criterio(tema="reteiva"), _criterio(tema="proceso"), _criterio()])

        temas = [c.tema for c in repo.list_all()]

        assert temas == sorted(temas)


class TestValidacion:
    def test_un_tema_desconocido_se_rechaza(self):
        """El tema decide cuándo entra el criterio al prompt; uno inventado no entraría nunca."""
        with pytest.raises(ValueError):
            RetentionCriterionItem(tema="inventado", pregunta="¿?", criterio="algo")

    def test_no_se_admite_un_criterio_vacio(self):
        with pytest.raises(ValueError):
            RetentionCriterionItem(tema="proceso", pregunta="¿?", criterio="")
