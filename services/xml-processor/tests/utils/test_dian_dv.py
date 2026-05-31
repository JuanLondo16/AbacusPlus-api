from app.utils.dian_dv import dv_calculate


class TestDvCalculate:
    def test_nit_with_known_dv(self):
        # NIT de la DIAN: 800197268-4
        assert dv_calculate("800197268") == 4

    def test_nit_nine_digits(self):
        # NIT conocido: 900123456-7
        result = dv_calculate("900123456")
        assert isinstance(result, int)
        assert 0 <= result <= 9

    def test_nit_single_digit(self):
        result = dv_calculate("1")
        assert isinstance(result, int)
        assert 0 <= result <= 9

    def test_nit_with_dots_and_dashes(self):
        # Debe filtrar solo digitos
        assert dv_calculate("800.197.268") == dv_calculate("800197268")

    def test_nit_with_letters_are_stripped(self):
        assert dv_calculate("800197268abc") == dv_calculate("800197268")

    def test_empty_string(self):
        result = dv_calculate("")
        assert result == 0

    def test_result_range(self):
        # DV siempre debe estar entre 0 y 9
        test_nits = ["800197268", "900000000", "123456789", "111111111"]
        for nit in test_nits:
            result = dv_calculate(nit)
            assert 0 <= result <= 9, f"DV para NIT {nit} fuera de rango: {result}"

    def test_consistency(self):
        # Mismo NIT siempre debe dar mismo DV
        nit = "800197268"
        results = [dv_calculate(nit) for _ in range(5)]
        assert len(set(results)) == 1
