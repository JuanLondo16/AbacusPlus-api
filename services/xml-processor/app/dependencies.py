import os
from fastapi import Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.infrastructure.config.database import get_db
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.clients.rag_client import RagClient
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase, GetDocumentByIdUseCase
from app.application.use_cases.query_receivers import GetAllReceiversUseCase

load_dotenv()


def get_rag_client() -> RagClient:
    url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
    return RagClient(base_url=url)


def get_process_xml_use_case(
    db: Session = Depends(get_db),
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


def get_documents_by_date_range_use_case(db: Session = Depends(get_db)) -> GetDocumentsByDateRangeUseCase:
    return GetDocumentsByDateRangeUseCase(document_repo=DocumentRepository(db))


def get_document_by_id_use_case(db: Session = Depends(get_db)) -> GetDocumentByIdUseCase:
    return GetDocumentByIdUseCase(document_repo=DocumentRepository(db))


def get_all_receivers_use_case(db: Session = Depends(get_db)) -> GetAllReceiversUseCase:
    return GetAllReceiversUseCase(receiver_repo=ReceiverRepository(db))
