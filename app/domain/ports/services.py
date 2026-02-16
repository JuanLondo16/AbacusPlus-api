from abc import ABC, abstractmethod


class PasswordHasherPort(ABC):
    @abstractmethod
    def hash(self, password: str) -> str:
        ...

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        ...


class TokenServicePort(ABC):
    @abstractmethod
    def create_token(self, data: dict) -> str:
        ...

    @abstractmethod
    def decode_token(self, token: str) -> dict:
        ...


class TextMatcherPort(ABC):
    @abstractmethod
    def match_score(self, text1: str, text2: str) -> float:
        ...
