"""Importación de tarifas de ReteICA por municipio — repunte de xml-processor a este
servicio. Mismas reglas de negocio que tenía `import_retention_rates.py` (solo la hoja
ReteICA), verificadas aquí sobre el nuevo destino (`integration_retentions`)."""

import pytest
from app.application.use_cases.import_retentions import ImportRetentionsUseCase
from app.domain.exceptions.base import ValidationException
from app.infrastructure.config.database import Base
from app.infrastructure.persistence.models.retention import Retention  # noqa: F401
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def use_case():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Retention.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield ImportRetentionsUseCase(RetentionRepository(session))
    finally:
        session.close()


def _excel(filas, headers=None, sheet_name="ReteICA"):
    headers = headers or ["codigo_municipio", "municipio", "concepto", "tarifa", "base_uvt"]
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for fila in filas:
        ws.append(fila)
    from io import BytesIO

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestImportacionBasica:
    def test_carga_una_fila(self, use_case):
        contenido = _excel([["11001", "Bogotá D.C.", "servicios", 9.66, 4]])

        resultado = use_case.execute(contenido)

        assert resultado.ica_loaded == 1
        assert resultado.retentions[0].municipality_code == "11001"

    def test_concepto_por_defecto_es_todos(self, use_case):
        contenido = _excel(
            [["11001", "Bogotá D.C.", None, 9.66, None]],
        )

        resultado = use_case.execute(contenido)

        assert resultado.retentions[0].retention_concept == "todos"

    def test_varias_filas_del_mismo_municipio_por_concepto(self, use_case):
        contenido = _excel(
            [
                ["11001", "Bogotá D.C.", "servicios", 9.66, 4],
                ["11001", "Bogotá D.C.", "compras", 11.04, 27],
            ]
        )

        resultado = use_case.execute(contenido)

        assert resultado.ica_loaded == 2


class TestValidaciones:
    def test_rechaza_fila_duplicada_municipio_concepto(self, use_case):
        contenido = _excel(
            [
                ["11001", "Bogotá D.C.", "servicios", 9.66, 4],
                ["11001", "Bogotá D.C.", "servicios", 10.0, 4],
            ]
        )

        with pytest.raises(ValidationException):
            use_case.execute(contenido)

    def test_rechaza_columnas_faltantes(self, use_case):
        contenido = _excel([[9.66]], headers=["tarifa"])

        with pytest.raises(ValidationException):
            use_case.execute(contenido)

    def test_rechaza_archivo_sin_filas(self, use_case):
        contenido = _excel([])

        with pytest.raises(ValidationException):
            use_case.execute(contenido)

    def test_rechaza_unidades_mezcladas(self, use_case):
        """9.66 es «por mil»; 1.1 en la misma tabla parece porcentaje. No se importa así."""
        contenido = _excel(
            [
                ["11001", "Bogotá D.C.", "servicios", 9.66, 4],
                ["11001", "Bogotá D.C.", "compras", 1.1, 27],
            ]
        )

        with pytest.raises(ValidationException, match="unidades distintas"):
            use_case.execute(contenido)

    def test_rechaza_hoja_ausente(self, use_case):
        contenido = _excel([["11001", "Bogotá D.C.", "servicios", 9.66, 4]], sheet_name="Otra")

        with pytest.raises(ValidationException, match="ReteICA"):
            use_case.execute(contenido)


class TestReplace:
    def test_replace_reemplaza_solo_lo_cargado(self, use_case):
        use_case.execute(_excel([["11001", "Bogotá D.C.", "servicios", 9.66, 4]]))

        resultado = use_case.execute(
            _excel([["05001", "Medellín", "servicios", 7.0, 15]]), replace=True
        )

        codigos = {r.municipality_code for r in resultado.retentions}
        assert codigos == {"05001"}
