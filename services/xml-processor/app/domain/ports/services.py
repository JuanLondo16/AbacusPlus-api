from abc import ABC, abstractmethod


class TextMatcherPort(ABC):
    @abstractmethod
    def match_score(self, text1: str, text2: str) -> float:
        ...
