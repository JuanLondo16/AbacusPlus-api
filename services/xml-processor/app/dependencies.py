import os
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.infrastructure.config.auth_dependency import get_tenant_db, get_token_data, TokenData
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.persistence.repositories.processing_log_repository import ProcessingLogRepository
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.clients.llm_client import LlmClient
from app.infrastructure.clients.odoo_client import OdooClient
from app.infrastructure.clients.accounting_rules_client import AccountingRulesClient
from app.infrastructure.queue.download_queue import get_queue
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.application.use_cases.process_downloads import ProcessDownloadsUseCase
from app.application.use_cases.process_single_file import ProcessSingleFileUseCase
from app.application.use_cases.query_documents import (
    GetDocumentsByDateRangeUseCase,
    GetDocumentByIdUseCase,
)
from app.application.use_cases.query_receivers import GetAllReceiversUseCase
from app.application.use_cases.query_issuers import GetIssuerByNitUseCase
from app.application.use_cases.get_document_detail import GetDocumentDetailWithAccountingUseCase
from app.application.use_cases.approve_document import ApproveDocumentUseCase, UnapproveDocumentUseCase
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository
from app.infrastructure.persistence.repositories.puc_repository import PucRepository
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository

load_dotenv()


def get_rag_client(token: Annotated[TokenData, Depends(get_token_data)]) -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url, bearer_token=token.raw_token)


def get_llm_client(token: Annotated[TokenData, Depends(get_token_data)]) -> LlmClient:
    url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8003")
    return LlmClient(base_url=url, bearer_token=token.raw_token)


def get_odoo_client(token: Annotated[TokenData, Depends(get_token_data)]) -> OdooClient:
    url = os.getenv("ODOO_SERVICE_URL", "http://odoo-service:8005")
    return OdooClient(base_url=url, bearer_token=token.raw_token)


def get_process_xml_use_case(
    db: Session = Depends(get_tenant_db),
    rag_client: RagClient = Depends(get_rag_client),
) -> ProcessXmlUseCase:
    return ProcessXmlUseCase(
        document_repo=DocumentRepository(db),
        issuer_repo=IssuerRepository(db),
        receiver_repo=ReceiverRepository(db),
        tax_repo=TaxRepository(db),
        concept_repo=ConceptRepository(db),
        rag_client=rag_client,
    )


def get_documents_by_date_range_use_case(db: Session = Depends(get_tenant_db)) -> GetDocumentsByDateRangeUseCase:
    return GetDocumentsByDateRangeUseCase(document_repo=DocumentRepository(db))


def get_document_by_id_use_case(db: Session = Depends(get_tenant_db)) -> GetDocumentByIdUseCase:
    return GetDocumentByIdUseCase(document_repo=DocumentRepository(db))


def get_all_receivers_use_case(db: Session = Depends(get_tenant_db)) -> GetAllReceiversUseCase:
    return GetAllReceiversUseCase(receiver_repo=ReceiverRepository(db))


def get_issuer_by_nit_use_case(db: Session = Depends(get_tenant_db)) -> GetIssuerByNitUseCase:
    return GetIssuerByNitUseCase(issuer_repo=IssuerRepository(db))


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


def get_accounting_rules_client(token: Annotated[TokenData, Depends(get_token_data)]) -> AccountingRulesClient:
    url = os.getenv("ACCOUNTING_RULES_SERVICE_URL", "http://accounting-rules-service:8009")
    return AccountingRulesClient(base_url=url, bearer_token=token.raw_token)


def get_approve_document_use_case(
    token: Annotated[TokenData, Depends(get_token_data)],
    db: Session = Depends(get_tenant_db),
) -> ApproveDocumentUseCase:
    llm_url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8003")
    rules_url = os.getenv("ACCOUNTING_RULES_SERVICE_URL", "http://accounting-rules-service:8009")
    return ApproveDocumentUseCase(
        document_repo=DocumentRepository(db),
        llm_client=LlmClient(base_url=llm_url, bearer_token=token.raw_token),
        accounting_rules_client=AccountingRulesClient(base_url=rules_url, bearer_token=token.raw_token),
    )


def get_unapprove_document_use_case(db: Session = Depends(get_tenant_db)) -> UnapproveDocumentUseCase:
    return UnapproveDocumentUseCase(document_repo=DocumentRepository(db))


def get_document_detail_use_case(
    db: Session = Depends(get_tenant_db),
    odoo_client: OdooClient = Depends(get_odoo_client),
    llm_client: LlmClient = Depends(get_llm_client),
) -> GetDocumentDetailWithAccountingUseCase:
    return GetDocumentDetailWithAccountingUseCase(
        document_repo=DocumentRepository(db),
        odoo_client=odoo_client,
        llm_client=llm_client,
    )
