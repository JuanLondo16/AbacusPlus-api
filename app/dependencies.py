import os
from fastapi import Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.infrastructure.config.database import get_db
from app.infrastructure.auth.password_hasher import BcryptPasswordHasher
from app.infrastructure.auth.jwt_service import JWTService
from app.infrastructure.persistence.repositories.user_repository import UserRepository
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.application.use_cases.manage_users import CreateUserUseCase, AuthenticateUserUseCase
from app.application.use_cases.query_documents import GetDocumentsByDateRangeUseCase, GetDocumentByIdUseCase
from app.application.use_cases.query_receivers import GetAllReceiversUseCase

load_dotenv()

_password_hasher = BcryptPasswordHasher()
_jwt_service = JWTService()
_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


def get_process_xml_use_case(db: Session = Depends(get_db)) -> ProcessXmlUseCase:
    return ProcessXmlUseCase(
        document_repo=DocumentRepository(db),
        issuer_repo=IssuerRepository(db),
        receiver_repo=ReceiverRepository(db),
        tax_repo=TaxRepository(db),
        concept_repo=ConceptRepository(db),
    )


def get_create_user_use_case(db: Session = Depends(get_db)) -> CreateUserUseCase:
    return CreateUserUseCase(
        user_repo=UserRepository(db),
        password_hasher=_password_hasher,
    )


def get_authenticate_user_use_case(db: Session = Depends(get_db)) -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        user_repo=UserRepository(db),
        password_hasher=_password_hasher,
        token_service=_jwt_service,
        expire_minutes=_expire_minutes,
    )


def get_documents_by_date_range_use_case(db: Session = Depends(get_db)) -> GetDocumentsByDateRangeUseCase:
    return GetDocumentsByDateRangeUseCase(
        document_repo=DocumentRepository(db),
    )


def get_document_by_id_use_case(db: Session = Depends(get_db)) -> GetDocumentByIdUseCase:
    return GetDocumentByIdUseCase(
        document_repo=DocumentRepository(db),
    )


def get_all_receivers_use_case(db: Session = Depends(get_db)) -> GetAllReceiversUseCase:
    return GetAllReceiversUseCase(
        receiver_repo=ReceiverRepository(db),
    )
