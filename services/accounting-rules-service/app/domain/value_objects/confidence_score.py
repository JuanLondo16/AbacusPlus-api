from app.domain.value_objects.match_level import MatchLevel

_REINFORCE_DELTA = 0.05
_PENALIZE_DELTA = 0.15
_DEFAULT_DECAY_FACTOR = 0.995


class ConfidenceScore:
    def __init__(self, value: float):
        self._value = max(0.0, min(1.0, value))

    @property
    def value(self) -> float:
        return self._value

    def reinforce(self) -> "ConfidenceScore":
        return ConfidenceScore(min(1.0, self._value + _REINFORCE_DELTA))

    def penalize(self) -> "ConfidenceScore":
        return ConfidenceScore(max(0.0, self._value - _PENALIZE_DELTA))

    def with_decay(
        self, months_idle: float, factor: float = _DEFAULT_DECAY_FACTOR
    ) -> "ConfidenceScore":
        return ConfidenceScore(self._value * (factor**months_idle))

    def classify(self, hit_threshold: float = 0.85, partial_threshold: float = 0.50) -> MatchLevel:
        if self._value >= hit_threshold:
            return MatchLevel.HIT
        if self._value >= partial_threshold:
            return MatchLevel.PARTIAL
        return MatchLevel.MISS

    def __float__(self) -> float:
        return self._value

    def __repr__(self) -> str:
        return f"ConfidenceScore({self._value:.4f})"
