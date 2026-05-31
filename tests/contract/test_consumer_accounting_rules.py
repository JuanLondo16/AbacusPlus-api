"""
Contract test consumidor: verifica que los payloads que llm-service
y xml-processor envían a accounting-rules-service son válidos.
"""

import schemathesis


def _rules_schema():
    return schemathesis.from_uri("http://localhost:18009/openapi.json")


def test_lookup_payload_matches_rules_contract():
    """llm-service envía este payload antes de llamar al LLM."""
    schema = _rules_schema()
    operation = schema["/api/v1/rules/lookups"]["POST"]
    case = operation.make_case(
        body={
            "nit": "900123456",
            "document_type": "INVOICE",
            "amount": 1500000.0,
            "description": "Servicios de consultoría",
        }
    )
    case.validate()


def test_approval_payload_matches_rules_contract():
    """xml-processor envía este payload al aprobar un documento."""
    schema = _rules_schema()
    operation = schema["/api/v1/rules/approvals"]["POST"]
    case = operation.make_case(
        body={
            "document_id": 42,
            "nit": "900123456",
            "document_type": "INVOICE",
            "amount": 1500000.0,
            "accounting_entries": [],
            "was_edited": False,
        }
    )
    case.validate()
