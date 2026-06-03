import numpy as np
import scipy.stats as ss
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import math

class OOSDeflationEngine:
    def __init__(self, periods_in_year: int = 252):
        self.periods_in_year = periods_in_year
        self.euler_mascheroni = 0.5772156649
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        self._elite_key = None
        self._elite_matrix = None

    def calculate_dsr(self, sharpe: float, skew: float, kurtosis: float,
                      track_record_length: int, num_trials: int, var_trials: float) -> float:
        var_trials = var_trials if var_trials > 0 else 1.0

        if num_trials < 2:
            expected_max_sr = 0.0
        else:
            term1 = (1 - self.euler_mascheroni) * ss.norm.ppf(1 - (1 / num_trials))
            term2 = self.euler_mascheroni * ss.norm.ppf(1 - (1 / (num_trials * math.e)))
            expected_max_sr = math.sqrt(var_trials) * (term1 + term2)

        annualized_sr = sharpe / math.sqrt(self.periods_in_year)

        skew_term = 1 - (skew * annualized_sr)
        kurt_term = ((kurtosis - 1) / 4) * (annualized_sr ** 2)
        variance_of_sr = skew_term + kurt_term

        if variance_of_sr <= 0:
            return 0.0

        std_dev_sr = math.sqrt(variance_of_sr / (max(2, track_record_length) - 1))

        dsr_z_stat = (annualized_sr - expected_max_sr) / std_dev_sr
        dsr_prob = ss.norm.cdf(dsr_z_stat)

        return sharpe * dsr_prob

    def fit_elite_population(self, elite_population: list):
        if not elite_population:
            self._elite_key = ()
            self._elite_matrix = None
            return

        elite_key = tuple(elite_population)
        if elite_key == self._elite_key and self._elite_matrix is not None:
            return

        try:
            self._elite_matrix = self.vectorizer.fit_transform(elite_population)
            self._elite_key = elite_key
        except Exception:
            self._elite_key = ()
            self._elite_matrix = None

    def calculate_orthogonal_fitness(self, candidate_expr: str, elite_population: list, base_fitness: float) -> float:
        if not elite_population:
            return base_fitness

        self.fit_elite_population(elite_population)
        if self._elite_matrix is None:
            return base_fitness

        try:
            candidate_matrix = self.vectorizer.transform([candidate_expr])
            similarities = cosine_similarity(candidate_matrix, self._elite_matrix)
            max_similarity = similarities.max()
        except Exception:
            max_similarity = 0.0

        orthogonal_multiplier = np.exp(-2.5 * (max_similarity ** 2))
        return base_fitness * orthogonal_multiplier

    def calculate_orthogonal_fitness_batch(self, candidate_exprs: list, elite_population: list, base_fitnesses: list) -> list:
        if not elite_population or not candidate_exprs:
            return list(base_fitnesses)

        self.fit_elite_population(elite_population)
        if self._elite_matrix is None:
            return list(base_fitnesses)

        try:
            candidate_matrix = self.vectorizer.transform(candidate_exprs)
            similarities = cosine_similarity(candidate_matrix, self._elite_matrix)
            max_similarities = similarities.max(axis=1)
        except Exception:
            max_similarities = np.zeros(len(candidate_exprs))

        multipliers = np.exp(-2.5 * (max_similarities ** 2))
        return [fitness * multiplier for fitness, multiplier in zip(base_fitnesses, multipliers)]
