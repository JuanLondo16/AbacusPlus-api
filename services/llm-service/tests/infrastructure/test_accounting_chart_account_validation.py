import pytest

from app.application.use_cases.generate_accounting_entry import GenerateAccountingEntryUseCase


class FakeChartAccountRepository:
    def __init__(self, accounts):
        self.accounts = {account["code"]: account for account in accounts}

    def list_active(self, provider: str, account_key: str):
        return list(self.accounts.values())

    def find_active_by_codes(self, provider: str, account_key: str, codes):
        return {
            code: self.accounts[code]
            for code in codes
            if code in self.accounts
        }


def _use_case(accounts):
    return GenerateAccountingEntryUseCase(
        ai_service=object(),
        document_client=object(),
        catalog_client=None,
        accounting_repo=object(),
        system_prompt_repo=object(),
        chart_account_repo=FakeChartAccountRepository(accounts),
    )


def test_validate_registered_accounts_accepts_active_registered_codes():
    accounts = [
        {"code": "510505", "name": "Gastos de personal"},
        {"code": "220500", "name": "Proveedores nacionales"},
    ]
    use_case = _use_case(accounts)
    entries = [
        {"cuenta": "510505", "nombre": "Nombre sugerido", "debito": 100.0, "credito": 0.0},
        {"cuenta": "220500", "nombre": "CxP", "debito": 0.0, "credito": 100.0},
    ]

    validated = use_case._validate_registered_accounts(entries, accounts)

    assert validated[0]["nombre"] == "Gastos de personal"
    assert validated[1]["nombre"] == "Proveedores nacionales"


def test_validate_registered_accounts_rejects_unregistered_codes():
    accounts = [{"code": "220500", "name": "Proveedores nacionales"}]
    use_case = _use_case(accounts)
    entries = [
        {"cuenta": "999999", "nombre": "No existe", "debito": 100.0, "credito": 0.0},
        {"cuenta": "220500", "nombre": "CxP", "debito": 0.0, "credito": 100.0},
    ]

    with pytest.raises(ValueError, match="999999"):
        use_case._validate_registered_accounts(entries, accounts)
