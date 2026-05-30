from enum import Enum


class MatchLevel(str, Enum):
    HIT = "HIT"
    PARTIAL = "PARTIAL"
    MISS = "MISS"
