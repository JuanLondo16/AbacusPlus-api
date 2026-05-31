from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.application.use_cases.manage_purchase_invoice_parameters import (
    ManagePurchaseInvoiceParametersUseCase,
)
from app.application.use_cases.send_journal_entry import SendJournalEntryUseCase
from app.application.use_cases.sync_chart_accounts import SyncChartAccountsUseCase
from app.infrastructure.config.auth_dependency import get_tenant_db
from app.infrastructure.persistence.repositories.chart_account_repository import (
    ChartAccountRepository,
)
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)
from app.infrastructure.persistence.repositories.purchase_invoice_parameter_repository import (
    PurchaseInvoiceParameterRepository,
)


def get_credentials_use_case(db: Session = Depends(get_tenant_db)) -> ManageCredentialsUseCase:
    return ManageCredentialsUseCase(IntegrationCredentialRepository(db))


def get_sync_chart_accounts_use_case(
    db: Session = Depends(get_tenant_db),
) -> SyncChartAccountsUseCase:
    credentials = ManageCredentialsUseCase(IntegrationCredentialRepository(db))
    return SyncChartAccountsUseCase(credentials=credentials, repository=ChartAccountRepository(db))


def get_purchase_invoice_parameters_use_case(
    db: Session = Depends(get_tenant_db),
) -> ManagePurchaseInvoiceParametersUseCase:
    return ManagePurchaseInvoiceParametersUseCase(PurchaseInvoiceParameterRepository(db))


def get_send_journal_entry_use_case(
    db: Session = Depends(get_tenant_db),
) -> SendJournalEntryUseCase:
    credentials = ManageCredentialsUseCase(IntegrationCredentialRepository(db))
    return SendJournalEntryUseCase(credentials=credentials)
