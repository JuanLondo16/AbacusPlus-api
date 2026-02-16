from dataclasses import dataclass


@dataclass(frozen=True)
class NIT:
    """Colombian Tax Identification Number with verification digit."""

    value: str
    verification_digit: int

    def __post_init__(self):
        cleaned = ''.join(filter(str.isdigit, self.value))
        if not cleaned:
            raise ValueError("NIT must contain at least one digit")
        object.__setattr__(self, 'value', cleaned)

    @staticmethod
    def calculate_dv(nit: str) -> int:
        """Compute DIAN verification digit for a given NIT."""
        weights = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]
        nit = ''.join(filter(str.isdigit, nit))
        total = 0
        for i, digit in enumerate(reversed(nit)):
            total += int(digit) * weights[-(i + 1)]
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    @classmethod
    def from_raw(cls, raw_nit: str) -> "NIT":
        """Create a NIT instance from a raw string, computing the DV automatically."""
        cleaned = ''.join(filter(str.isdigit, raw_nit))
        dv = cls.calculate_dv(cleaned)
        return cls(value=cleaned, verification_digit=dv)

    def __str__(self) -> str:
        return f"{self.value}-{self.verification_digit}"
