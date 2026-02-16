from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import date

from app.domain.entities.user import UserEntity
from app.domain.entities.document import DocumentEntity
from app.domain.entities.receiver import ReceiverEntity
from app.domain.entities.issuer import IssuerEntity
from app.domain.entities.tax import TaxEntity
from app.domain.entities.concept import ConceptDescriptionEntity


class UserRepositoryPort(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> Optional[object]:
        ...

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[object]:
        ...

    @abstractmethod
    def create(self, user: object) -> object:
        ...

    @abstractmethod
    def update_last_login(self, user: object) -> None:
        ...


class DocumentRepositoryPort(ABC):
    @abstractmethod
    def get_by_document_number(self, document_number: str) -> Optional[object]:
        ...

    @abstractmethod
    def get_by_id(self, document_id: int) -> Optional[object]:
        ...

    @abstractmethod
    def get_by_date_range(self, date_start: date, date_end: date) -> List[object]:
        ...

    @abstractmethod
    def create(self, document: object) -> object:
        ...


class ReceiverRepositoryPort(ABC):
    @abstractmethod
    def get_by_nit(self, nit: str) -> Optional[object]:
        ...

    @abstractmethod
    def get_all(self) -> List[object]:
        ...

    @abstractmethod
    def create(self, receiver: object) -> object:
        ...


class IssuerRepositoryPort(ABC):
    @abstractmethod
    def get_by_nit(self, nit: str) -> Optional[object]:
        ...

    @abstractmethod
    def create(self, issuer: object) -> object:
        ...


class TaxRepositoryPort(ABC):
    @abstractmethod
    def get_by_receiver_and_name(self, receiver_nit: str, tax_name: str) -> Optional[object]:
        ...

    @abstractmethod
    def create(self, tax: object) -> object:
        ...


class ConceptRepositoryPort(ABC):
    @abstractmethod
    def get_descriptions_by_receiver(self, receiver_nit: str) -> List[object]:
        ...

    @abstractmethod
    def find_matching_description(self, receiver_nit: str, description: str) -> Optional[object]:
        ...

    @abstractmethod
    def create_description(self, concept_desc: object) -> object:
        ...
