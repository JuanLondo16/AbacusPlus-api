"""
Contract test productor: verifica que rag-service implementa
exactamente lo que documenta en su spec OpenAPI.
"""

import schemathesis

schema = schemathesis.from_uri("http://localhost:18002/openapi.json")


@schema.parametrize()
def test_rag_api(case):
    case.call_and_validate()
