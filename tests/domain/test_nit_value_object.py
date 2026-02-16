import pytest
from app.domain.value_objects.nit import NIT


class TestNIT:
    def test_from_raw_known_dv(self):
        nit = NIT.from_raw("800197268")
        assert nit.verification_digit == 4
        assert nit.value == "800197268"

    def test_from_raw_strips_non_digits(self):
        nit = NIT.from_raw("800.197.268")
        assert nit.value == "800197268"
        assert nit.verification_digit == 4

    def test_str_representation(self):
        nit = NIT.from_raw("800197268")
        assert str(nit) == "800197268-4"

    def test_frozen_immutability(self):
        nit = NIT.from_raw("800197268")
        with pytest.raises(AttributeError):
            nit.value = "999999999"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must contain at least one digit"):
            NIT(value="", verification_digit=0)

    def test_no_digits_raises(self):
        with pytest.raises(ValueError, match="must contain at least one digit"):
            NIT(value="abc", verification_digit=0)

    def test_calculate_dv_consistency(self):
        results = [NIT.calculate_dv("800197268") for _ in range(5)]
        assert len(set(results)) == 1

    def test_calculate_dv_range(self):
        test_nits = ["800197268", "900000000", "123456789", "111111111"]
        for nit in test_nits:
            result = NIT.calculate_dv(nit)
            assert 0 <= result <= 9
