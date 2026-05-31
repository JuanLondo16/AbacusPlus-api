"""
Contract test consumidor: verifica que los payloads que xml-processor
y llm-service envían a rag-service son válidos según su spec OpenAPI.
"""

import schemathesis


def _rag_schema():
    return schemathesis.from_uri("http://localhost:18002/openapi.json")


def test_index_chunk_payload_matches_rag_contract():
    """xml-processor envía este payload al indexar un fragmento."""
    schema = _rag_schema()
    operation = schema["/api/v1/chunks"]["POST"]
    case = operation.make_case(
        body={
            "content": "Factura de compra proveedor ABC",
            "document_id": 1,
            "chunk_index": 0,
            "metadata": {"source": "xml-processor"},
        }
    )
    case.validate()


def test_search_chunks_payload_matches_rag_contract():
    """llm-service envía este payload al buscar contexto RAG."""
    schema = _rag_schema()
    operation = schema["/api/v1/chunks/search"]["POST"]
    case = operation.make_case(
        body={
            "query": "¿Cuánto IVA pagó el proveedor ABC en marzo?",
            "top_k": 5,
        }
    )
    case.validate()
