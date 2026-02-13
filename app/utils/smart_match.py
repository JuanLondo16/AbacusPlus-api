import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def similarity_levenshtein(string1, string2):
    distance = Levenshtein.distance(string1, string2)
    max_distance = max(len(string1), len(string2))
    return (1 - distance / max_distance) * 100

def similarity_cosine(string1, string2):
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([string1, string2])
    return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0] * 100

def smart_match(string1, string2):
    weight_levenshtein = 0.4
    weight_cosine = 0.6
    levenshtein_similarity = similarity_levenshtein(string1, string2)
    cosine_similarity = similarity_cosine(string1, string2)
    return (weight_levenshtein * levenshtein_similarity + weight_cosine * cosine_similarity) / (weight_levenshtein + weight_cosine)
    