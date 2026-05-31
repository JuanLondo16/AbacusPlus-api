from app.utils.smart_match import (
    similarity_cosine,
    similarity_levenshtein,
    smart_match,
)


class TestSimilarityLevenshtein:
    def test_identical_strings(self):
        assert similarity_levenshtein("hello", "hello") == 100.0

    def test_completely_different(self):
        result = similarity_levenshtein("abc", "xyz")
        assert result < 50

    def test_one_char_difference(self):
        result = similarity_levenshtein("hello", "hallo")
        assert result > 70

    def test_empty_vs_nonempty(self):
        result = similarity_levenshtein("", "hello")
        assert result == 0.0


class TestSimilarityCosine:
    def test_identical_strings(self):
        result = similarity_cosine("factura electronica", "factura electronica")
        assert result > 99

    def test_different_strings(self):
        result = similarity_cosine("factura electronica", "zapato deportivo")
        assert result < 50

    def test_similar_strings(self):
        result = similarity_cosine(
            "servicio de transporte urbano",
            "servicio transporte urbano",
        )
        assert result > 70


class TestSmartMatch:
    def test_identical_strings(self):
        result = smart_match("servicio de limpieza", "servicio de limpieza")
        assert result > 95

    def test_very_similar_strings(self):
        result = smart_match(
            "servicio de transporte",
            "servicio transporte urbano",
        )
        assert result > 50

    def test_completely_different(self):
        result = smart_match("abc xyz", "123 456")
        assert result < 30

    def test_threshold_boundary(self):
        # Strings similares deben tener score alto
        result = smart_match(
            "mantenimiento de equipos",
            "mantenimiento equipos",
        )
        assert result > 75

    def test_returns_float(self):
        result = smart_match("test", "test")
        assert isinstance(result, float)
