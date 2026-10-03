```python
import logging
import math

import numpy as np
import scipy.stats as ss
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from syntax_validator import SyntaxValidator

logger = logging.getLogger(__name__)

# Euler-Mascheroni constant, used in the expected-maximum-Sharpe estimator.
_EULER_GAMMA = 0.5772156649015329


class OOSDeflationEngine:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado) + diversity shaping.

    CRITICAL UNIT CONVENTION
    ------------------------
    Every quantity inside the DSR computation is expressed in PER-PERIOD units
    (i.e. per trading day), never annualized. The public API takes an annualized
    Sharpe (as the platform reports it) and de-annualizes it ONCE here, and it
    expects `var_trials` to already be the variance of the PER-PERIOD trial
    Sharpes. Mixing annualized and per-period quantities was the original bug
    that drove the deflated score to ~0 for every alpha.

    KURTOSIS CONVENTION
    -------------------
    `kurtosis` is interpreted as EXCESS kurtosis (normal == 0) when
    config.KURTOSIS_IS_EXCESS is True (the default; matches WorldQuant and
    scipy.stats.kurtosis). It is converted to the full fourth standardized
    moment gamma_4 (normal == 3) before use, which is what Bailey & Lopez de
    Prado (2014) require.
    """

    def __init__(self, periods_in_year: int = config.PERIODS_IN_YEAR):
        self.periods_in_year = max(1, int(periods_in_year))
        self._sqrt_periods = math.sqrt(self.periods_in_year)

    def _expected_max_sharpe(self, num_trials: int, var_trials: float) -> float:
        """Expected maximum of `num_trials` i.i.d. per-period Sharpe estimates."""
        if num_trials < 2 or var_trials <= 0:
            return 0.0
        # Cap the effective trial count (A3). count_trials() grows every
        # generation, so an uncapped num_trials makes the multiple-testing
        # benchmark (this expected-max-Sharpe hurdle) creep upward forever and
        # slowly crush late-run deflated fitness toward 0 -- i.e. alphas get
        # penalized merely because the engine has been RUNNING longer, not for
        # being weaker. Capping keeps deflation a stable statistical guard rather
        # than an ever-tightening ratchet; since the expected max grows only ~as
        # sqrt(2 ln N), a generous cap barely moves the bar in the normal regime
        # and only prevents the pathological runaway. <=1 disables the cap.
        cap = getattr(config, "DEFLATION_MAX_TRIALS", 0)
        if cap and cap > 1 and num_trials > cap:
            num_trials = cap
        sigma = math.sqrt(var_trials)
        z1 = ss.norm.ppf(1.0 - 1.0 / num_trials)
        z2 = ss.norm.ppf(1.0 - 1.0 / (num_trials * math.e))
        return sigma * ((1.0 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2)

    def calculate_dsr(self, sharpe: float, skew: float, kurtosis: float,
                      track_record_length: int, num_trials: int,
                      var_trials: float) -> float:
        """Return a confidence-weighted (deflated) Sharpe.

        Output = annualized_sharpe * P(true SR > expected-max-SR | multiple
        testing). The probability lives in [0, 1], so a strong, statistically
        robust alpha keeps most of its Sharpe while an over-fit one is pulled
        toward 0. All internal math is per-period.
        """
        if sharpe is None or not math.isfinite(sharpe):
            return 0.0

        n = max(2, int(track_record_length or config.DEFAULT_TRACK_RECORD_LENGTH))
        sr = sharpe / self._sqrt_periods  # de-annualize ONCE

        # Convert to the full fourth standardized moment gamma_4 (normal == 3),
        # which the Bailey & Lopez de Prado SR-variance formula expects. The
        # platform reports EXCESS kurtosis (normal == 0), so using (kurtosis-1)
        # directly underestimated the variance and over-stated confidence for
        # fat-tailed alphas. Note (gamma_4 - 1) == (excess_kurtosis + 2).
        gamma4 = kurtosis + 3.0 if config.KURTOSIS_IS_EXCESS else kurtosis
        # Variance of the (per-period) Sharpe estimator under non-normality.
        sr_var = (1.0 - skew * sr + ((gamma4 - 1.0) / 4.0) * sr * sr) / (n - 1)
        if not math.isfinite(sr_var) or sr_var <= 0:
            return 0.0
        sr_std = math.sqrt(sr_var)

        sr0 = self._expected_max_sharpe(num_trials, var_trials)
        z = (sr - sr0) / sr_std
        probability = float(ss.norm.cdf(z))
        return sharpe * probability

    def calculate_orthogonal_fitness_batch(self, expressions, reference_expressions,
                                           base_fitnesses):
        """Soft diversity shaping using a STRUCTURAL string proxy.

        This is intentionally a cheap proxy (character n-gram TF-IDF over the
        formula text) used only to gently discourage structurally near-identical
        candidates inside the search loop. It does NOT measure return
        correlation. The authoritative decorrelation check is realized
        self-correlation from the WorldQuant /correlations/self endpoint, which
        the orchestrator applies as a HARD gate before promoting or submitting
        an alpha. See orchestrator._check_correlation.
        """
        if not expressions:
            return []
        if not reference_expressions:
            return list(base_fitnesses)

        try:
            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
            corpus = list(reference_expressions) + list(expressions)
            matrix = vectorizer.fit_transform(corpus)
            ref_count = len(reference_expressions)
            ref_matrix = matrix[:ref_count]
            cand_matrix = matrix[ref_count:]
            similarities = cosine_similarity(cand_matrix, ref_matrix)
        except Exception as e:
            logger.warning(f"Diversity shaping skipped ({e}); using raw fitness.")
            return list(base_fitnesses)

        adjusted = []
        for i, base in enumerate(base_fitnesses):
            max_sim = float(similarities[i].max()) if similarities[i].size else 0.0
            # Penalize structural redundancy smoothly in (0, 1].
            multiplier = math.exp(-2.5 * max_sim * max_sim)
            adjusted.append(base * multiplier)
        return adjusted

    @staticmethod
    def _aligned_pnl_increments(a, b, min_overlap):
        """Daily PnL INCREMENTS of two cumulative-PnL dicts ({date: cum_pnl}) on
        their shared dates. Returns (inc_a, inc_b) as numpy arrays, or
        (None, None) when fewer than min_overlap increments overlap."""
        common = sorted(set(a) & set(b))
        if len(common) < min_overlap + 1:
            return None, None
        va = np.asarray([a[d] for d in common], dtype=float)
        vb = np.asarray([b[d] for d in common], dtype=float)
        return np.diff(va), np.diff(vb)

    def calculate_return_orthogonal_fitness_batch(self, candidate_pnls, elite_pnls,
                                                  base_fitnesses, min_overlap=30,
                                                  k=2.5):
        """RETURNS-based diversity shaping -- the authoritative complement to the
        STRUCTURAL string proxy in calculate_orthogonal_fitness_batch. For each
        candidate, compute the max |correlation| of its DAILY PnL increments
        against the elite basket and damp a POSITIVE adjusted-DSR by
        exp(-k * corr^2). This penalizes an alpha that merely re-expresses the
        dominant return stream even when its SYNTAX is novel, so selection breeds
        toward PnL-orthogonal alphas (raising effective bet count / ENB).

        candidate_pnls / elite_pnls: lists of {date: cumulative_pnl} dicts (a
        candidate entry may be None). An empty elite basket, a missing candidate
        series, or too little date overlap all leave the fitness UNCHANGED, so
        the lever degrades gracefully to structural-only shaping and never blocks
        the first winners."""
        if not elite_pnls:
            return list(base_fitnesses)
        adjusted = []
        for cand, base in zip(candidate_pnls, base_fitnesses):
            if not cand or base <= 0:
                adjusted.append(base)
                continue
            max_corr = 0.0
            for elite in elite_pnls:
                if not elite:
                    continue
                inc_c, inc_e = self._aligned_pnl_increments(cand, elite, min_overlap)
                if inc_c is None or inc_c.size < 2:
                    continue
                if inc_c.std() <= 0 or inc_e.std() <= 0:
                    continue
                try:
                    corr = float(np.corrcoef(inc_c, inc_e)[0, 1])
                except Exception:
                    continue
                if math.isfinite(corr):
                    max_corr = max(max_corr, abs(corr))
            adjusted.append(base * math.exp(-k * max_corr * max_corr))
        return adjusted

    @staticmethod
    def structural_similarity(expression: str, reference_expressions) -> float:
        """Max structural similarity of `expression` vs a set of references."""
        if not reference_expressions:
            return 0.0
        try:
            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
            matrix = vectorizer.fit_transform(list(reference_expressions) + [expression])
            sims = cosine_similarity(matrix[-1:], matrix[:-1])
            return float(sims.max()) if sims.size else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def ast_similarity(expression: str, reference_expressions) -> float:
        """AST-motif Jaccard similarity (max over references) -- Upgrade #4.

        Unlike `structural_similarity` (a char-ngram string proxy), this compares
        abstracted call-subtree motifs, so it catches structural twins that read
        differently as text and ignores cosmetic field/window swaps. Used for
        near-duplicate de-duplication and originality-vs-zoo scoring.
        """
        try:
            return SyntaxValidator.motif_similarity(expression, list(reference_expressions or []))
        except Exception:
            return 0.0

    def overfitting_risk_multiplier(self, is_sharpe, oos_sharpe) -> float:
        """Fitness multiplier in (0, 1] penalizing a wide IS-OOS gap (Upgrade #6).

        Neutral (1.0) when no OOS figure is available. Otherwise the penalty
        grows with the RELATIVE shortfall of OOS vs IS Sharpe -- the textbook
        over-fit signature (IS keeps climbing while OOS lags).
        """
        if not config.OVERFIT_RISK_ENABLED or oos_sharpe is None:
            return 1.0
        try:
            is_s = float(is_sharpe)
            oos_s = float(oos_sharpe)
        except (TypeError, ValueError):
            return 1.0
        if not (math.isfinite(is_s) and math.isfinite(oos_s)) or is_s <= 0:
            return 1.0
        gap = max(0.0, is_s - oos_s) / is_s   # relative shortfall
        return float(math.exp(-config.OVERFIT_RISK_K * gap))

    @staticmethod
    def estimate_pbo(is_oos_pairs) -> float:
        """Simplified Probability of Backtest Overfitting (CSCV-flavoured).

        Given (is_score, oos_score) pairs, estimate how over-fit the IS winner is
        by the fraction of trials whose OOS score beats the IS winner's OOS
        score. High => the in-sample champion is mediocre out-of-sample. This is
        an APPROXIMATION (true CSCV needs per-period returns we don't retain),
        logged as a portfolio diagnostic, never used as a hard gate.
        """
        pairs = [(i, o) for i, o in (is_oos_pairs or [])
                 if i is not None and o is not None
                 and math.isfinite(i) and math.isfinite(o)]
        if len(pairs) < 4:
            return 0.0
        best_is_oos = max(pairs, key=lambda p: p[0])[1]
        worse = sum(1 for _, o in pairs if o > best_is_oos)
        return float(worse) / len(pairs)


def _self_test():
    """Sanity check: a strong alpha must out-score a weak one under identical
    multiple-testing pressure (this would FAIL under the old unit-mismatched
    implementation, which collapsed every score to ~0)."""
    engine = OOSDeflationEngine()
    per_period_var = (0.4 / math.sqrt(config.PERIODS_IN_YEAR)) ** 2
    # kurtosis here is EXCESS (1.0 == mildly fat-tailed); see KURTOSIS_IS_EXCESS.
    strong = engine.calculate_dsr(2.5, 0.1, 1.0, 252, num_trials=500, var_trials=per_period_var)
    weak = engine.calculate_dsr(0.4, 0.1, 1.0, 252, num_trials=500, var_trials=per_period_var)
    print(f"strong DSR={strong:.4f}  weak DSR={weak:.4f}")
    assert strong > weak, "DSR must reward a higher, more robust Sharpe"
    assert strong > 0.0, "A strong alpha should retain positive deflated Sharpe"
    print("oos_deflation self-test passed.")


if __name__ == "__main__":
    _self_test()
```