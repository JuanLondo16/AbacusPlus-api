import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.approve_document import (
    ApproveDocumentUseCase,
    UnapproveDocumentUseCase,
)
from app.application.use_cases.get_document_detail import GetDocumentDetailWithAccountingUseCase
from app.application.use_cases.process_downloads import ProcessDownloadsUseCase
from app.application.use_cases.process_single_file import ProcessSingleFileUseCase
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.application.use_cases.query_documents import (
    GetDocumentByIdUseCase,
    GetDocumentsByDateRangeUseCase,
)
from app.application.use_cases.query_issuers import GetIssuerByNitUseCase
from app.application.use_cases.query_receivers import GetAllReceiversUseCase
from app.infrastructure.clients.integration_config_client import IntegrationConfigClient
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.auth_dependency import TokenData, get_tenant_db, get_token_data
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.processing_log_repository import (
    ProcessingLogRepository,
)
from app.infrastructure.persistence.repositories.puc_repository import PucRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.queue.download_queue import get_queue

load_dotenv()


def get_rag_client(token: Annotated[TokenData, Depends(get_token_data)]) -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url, bearer_token=token.raw_token)


def get_integration_config_client(
    token: Annotated[TokenData, Depends(get_token_data)],
) -> IntegrationConfigClient:
    url = os.getenv("INTEGRATION_CONFIG_URL", "http://integration-config-service:8007")
    return IntegrationConfigClient(base_url=url, bearer_token=token.raw_token)



def get_process_xml_use_case(
    db: Session = Depends(get_tenant_db),
    rag_client: RagClient = Depends(get_rag_client),
    integration_config_client: IntegrationConfigClient = Depends(get_integration_config_client),
) -> ProcessXmlUseCase:
    return ProcessXmlUseCase(
        document_repo=DocumentRepository(db),
        issuer_repo=IssuerRepository(db),
        receiver_repo=ReceiverRepository(db),
        tax_repo=TaxRepository(db),
        concept_repo=ConceptRepository(db),
        rag_client=rag_client,
        integration_config_client=integration_config_client,
    )


def get_documents_by_date_range_use_case(
    db: Session = Depends(get_tenant_db),
) -> GetDocumentsByDateRangeUseCase:
    return GetDocumentsByDateRangeUseCase(document_repo=DocumentRepository(db))


def get_document_by_id_use_case(db: Session = Depends(get_tenant_db)) -> GetDocumentByIdUseCase:
    return GetDocumentByIdUseCase(document_repo=DocumentRepository(db))


def get_all_receivers_use_case(db: Session = Depends(get_tenant_db)) -> GetAllReceiversUseCase:
    return GetAllReceiversUseCase(receiver_repo=ReceiverRepository(db))


def get_issuer_by_nit_use_case(db: Session = Depends(get_tenant_db)) -> GetIssuerByNitUseCase:
    return GetIssuerByNitUseCase(issuer_repo=IssuerRepository(db))


def get_document_repo(db: Session = Depends(get_tenant_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_concept_repo(db: Session = Depends(get_tenant_db)) -> ConceptRepository:
    return ConceptRepository(db)


def get_cost_center_repo(db: Session = Depends(get_tenant_db)) -> CostCenterRepository:
    return CostCenterRepository(db)


def get_puc_repo(db: Session = Depends(get_tenant_db)) -> PucRepository:
    return PucRepository(db)


def get_retention_repo(db: Session = Depends(get_tenant_db)) -> RetentionRepository:
    return RetentionRepository(db)


def get_process_downloads_use_case() -> ProcessDownloadsUseCase:
    return ProcessDownloadsUseCase(
        downloads_dir=os.getenv("DOWNLOADS_DIR", "/app/downloads"),
        queue=get_queue(),
    )


def get_process_single_file_use_case() -> ProcessSingleFileUseCase:
    return ProcessSingleFileUseCase(
        downloads_dir=os.getenv("DOWNLOADS_DIR", "/app/downloads"),
        queue=get_queue(),
    )


def get_processing_log_repo(db: Session = Depends(get_tenant_db)) -> ProcessingLogRepository:
    return ProcessingLogRepository(db)



def get_approve_document_use_case(
    db: Session = Depends(get_tenant_db),
) -> ApproveDocumentUseCase:
    return ApproveDocumentUseCase(document_repo=DocumentRepository(db))


def get_unapprove_document_use_case(
    db: Session = Depends(get_tenant_db),
) -> UnapproveDocumentUseCase:
    return UnapproveDocumentUseCase(document_repo=DocumentRepository(db))


def get_document_detail_use_case(
    db: Session = Depends(get_tenant_db),
) -> GetDocumentDetailWithAccountingUseCase:
    return GetDocumentDetailWithAccountingUseCase(document_repo=DocumentRepository(db))
