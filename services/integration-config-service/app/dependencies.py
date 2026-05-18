from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.application.use_cases.import_chart_accounts import ImportChartAccountsUseCase
from app.application.use_cases.import_cost_centers import ImportCostCentersUseCase
from app.application.use_cases.manage_purchase_invoice_parameters import ManagePurchaseInvoiceParametersUseCase
from app.infrastructure.config.database import get_db
from app.infrastructure.persistence.repositories.chart_account_repository import ChartAccountRepository
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository
from app.infrastructure.persistence.repositories.integration_repository import IntegrationCredentialRepository
from app.infrastructure.persistence.repositories.purchase_invoice_parameter_repository import (
    PurchaseInvoiceParameterRepository,
)


def get_credentials_use_case(db: Session = Depends(get_db)) -> ManageCredentialsUseCase:
    return ManageCredentialsUseCase(IntegrationCredentialRepository(db))


def get_purchase_invoice_parameters_use_case(
    db: Session = Depends(get_db),
) -> ManagePurchaseInvoiceParametersUseCase:
    return ManagePurchaseInvoiceParametersUseCase(PurchaseInvoiceParameterRepository(db))


def get_import_chart_accounts_use_case(db: Session = Depends(get_db)) -> ImportChartAccountsUseCase:
    return ImportChartAccountsUseCase(ChartAccountRepository(db))


def get_import_cost_centers_use_case(db: Session = Depends(get_db)) -> ImportCostCentersUseCase:
    return ImportCostCentersUseCase(CostCenterRepository(db))
