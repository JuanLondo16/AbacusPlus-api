import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def similarity_levenshtein(string1, string2):
    """Similitud basada en distancia de edición, normalizada a 0-100.

    Captura errores tipográficos y variaciones de caracteres a nivel local
    (abreviaciones, errores ortográficos, acentos omitidos).
    """
    distance = Levenshtein.distance(string1, string2)
    max_distance = max(len(string1), len(string2))
    return (1 - distance / max_distance) * 100


def similarity_cosine(string1, string2):
    """Similitud semántica TF-IDF por coseno, normalizada a 0-100.

    Captura diferencias de vocabulario y orden de palabras que Levenshtein
    penalizaría injustamente (ej: "papel bond A4" vs "A4 papel bond").
    """
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([string1, string2])
    return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0] * 100


def smart_match(string1, string2):
    """Similitud híbrida ponderada entre dos cadenas, resultado en escala 0-100.

    Combina Levenshtein (peso 0.4) para capturar typos/abreviaciones con
    TF-IDF coseno (peso 0.6) para capturar diferencias semánticas y de orden.
    El peso mayor en coseno refleja que las descripciones de ítems DIAN varían
    más en vocabulario que en ortografía.

    El denominador normaliza en caso de que los pesos se ajusten en el futuro.
    """
    weight_levenshtein = 0.4
    weight_cosine = 0.6
    levenshtein_similarity = similarity_levenshtein(string1, string2)
    cosine_sim = similarity_cosine(string1, string2)
    # Dividir por la suma de pesos para que el resultado sea siempre 0-100,
    # independiente de los valores de los pesos.
    return (weight_levenshtein * levenshtein_similarity + weight_cosine * cosine_sim) / (
        weight_levenshtein + weight_cosine
    )
