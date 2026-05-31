"""
Contract test productor: verifica que accounting-rules-service implementa
exactamente lo que documenta en su spec OpenAPI.
"""

import schemathesis

schema = schemathesis.from_uri("http://localhost:18009/openapi.json")


@schema.parametrize()
def test_accounting_rules_api(case):
    case.call_and_validate()
