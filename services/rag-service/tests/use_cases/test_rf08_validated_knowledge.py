"""RF-08 en el rag-service: qué puede entrar como conocimiento y qué puede recuperarse.

El rag-service no sabe nada del ciclo de vida contable —no conoce estados ni SIIGO—, así que
su parte del requisito se reduce a dos garantías que sí puede dar por sí mismo: no aceptar
conocimiento validado sin la prueba de que se contabilizó, y saber devolver únicamente ese
conocimiento cuando se lo piden.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.application.dto.chunk import IndexChunkRequest, SearchRequest
from app.application.use_cases.index_chunk import IndexChunkUseCase
from app.application.use_cases.search_chunks import SearchChunksUseCase
from app.domain.entities.chunk import ChunkEntity
from pydantic import ValidationError


@pytest.fixture
def fake_embedding_service():
    svc = AsyncMock()
    svc.embed = AsyncMock(return_value=[0.1] * 1536)
    return svc


@pytest.fixture
def fake_chunk_repo():
    repo = MagicMock()
    repo.create = MagicMock(
        side_effect=lambda chunk: ChunkEntity(
            id=1,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            content=chunk.content,
            is_validated=chunk.is_validated,
            validated_at=chunk.validated_at,
            siigo_id=chunk.siigo_id,
        )
    )
    repo.search_similar = MagicMock(return_value=[])
    return repo


class TestConocimientoValidado:
    def test_no_se_admite_conocimiento_validado_sin_comprobante_de_siigo(self):
        """Sin `siigo_id` no consta que la causación llegara a contabilizarse."""
        with pytest.raises(ValidationError):
            IndexChunkRequest(
                source_type="invoice", source_id=1, content="texto", is_validated=True
            )

    def test_un_chunk_normal_no_es_conocimiento_validado(self):
        request = IndexChunkRequest(source_type="invoice", source_id=1, content="texto")
        assert request.is_validated is False

    async def test_indexar_conocimiento_marca_el_chunk_y_lo_fecha(
        self, fake_chunk_repo, fake_embedding_service
    ):
        use_case = IndexChunkUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )

        result = await use_case.execute(
            IndexChunkRequest(
                source_type="invoice",
                source_id=42,
                content="causación contabilizada",
                is_validated=True,
                siigo_id="a1b2c3",
            )
        )

        guardado = fake_chunk_repo.create.call_args[0][0]
        assert result.is_validated is True
        assert guardado.is_validated is True
        assert guardado.siigo_id == "a1b2c3"
        assert guardado.validated_at is not None

    async def test_un_chunk_sin_validar_no_se_fecha(
        self, fake_chunk_repo, fake_embedding_service
    ):
        use_case = IndexChunkUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )

        await use_case.execute(
            IndexChunkRequest(source_type="file", content="un documento cualquiera")
        )

        guardado = fake_chunk_repo.create.call_args[0][0]
        assert guardado.is_validated is False
        assert guardado.validated_at is None


class TestRecuperacionDeConocimiento:
    async def test_la_busqueda_puede_restringirse_al_conocimiento_validado(
        self, fake_chunk_repo, fake_embedding_service
    ):
        use_case = SearchChunksUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )

        await use_case.execute(SearchRequest(query="retenciones", only_validated=True))

        assert fake_chunk_repo.search_similar.call_args.kwargs["only_validated"] is True

    async def test_por_defecto_la_busqueda_no_filtra(
        self, fake_chunk_repo, fake_embedding_service
    ):
        """La consulta documental general sigue viendo todo lo indexado.

        El filtro de RF-08 aplica a las sugerencias contables, no a la búsqueda libre sobre
        los documentos del cliente, que es otra funcionalidad con otro propósito.
        """
        use_case = SearchChunksUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=fake_embedding_service
        )

        await use_case.execute(SearchRequest(query="facturas de agosto"))

        assert fake_chunk_repo.search_similar.call_args.kwargs["only_validated"] is False


class TestLaDimensionDelEmbeddingSeComprueba:
    """Un vector que no cabe en la columna debe decirlo, no perderse en un warning.

    La indexación de RF-08 es best-effort: quien la llama se traga el error y sigue. Si el
    proveedor de embeddings no coincide con la columna, el sistema contabilizaría con
    normalidad y no aprendería nada, y nadie lo notaría hasta preguntarse por qué el RAG está
    vacío meses después.
    """

    @pytest.mark.asyncio
    async def test_rechaza_un_vector_de_otra_dimension(self, fake_chunk_repo):
        class _EmbeddingDeOtraDimension:
            async def embed(self, text):
                return [0.1] * 768  # Ollama, cuando la columna espera 1536.

        use_case = IndexChunkUseCase(
            chunk_repo=fake_chunk_repo, embedding_service=_EmbeddingDeOtraDimension()
        )

        with pytest.raises(ValueError, match="768.*1536|dimensiones"):
            await use_case.execute(
                IndexChunkRequest(
                    source_type="invoice",
                    source_id=1,
                    content="causación",
                    is_validated=True,
                    siigo_id="SIIGO-1",
                )
            )
