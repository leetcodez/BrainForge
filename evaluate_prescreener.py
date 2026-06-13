"""Offline, read-only evaluation of the surrogate pre-screener.

Trains on a time-ordered split of alpha_population and reports, at several skip
thresholds, how many simulations it WOULD have saved and how many real winners
it WOULD have wrongly skipped (false negatives). Run this BEFORE ever enabling
the surrogate on the hot path.

    python evaluate_prescreener.py
"""
import math

import numpy as np

import config
from surrogate_prescreener import load_dataset, _new_classifier


def _wilson_upper(k, n, z=1.96):
    """Upper bound of the Wilson score interval for a binomial proportion k/n.
    Used to report how high the false-negative rate could plausibly be given a
    small number of test winners -- a point-estimate FNR of 0% on a dozen
    winners is noise, so only trust a threshold whose UPPER bound is ~0."""
    if n <= 0:
        return 1.0
    phat = k / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return min(1.0, (centre + margin) / denom)


def main():
    X, y = load_dataset()
    X, y = np.array(X, dtype=float), np.array(y, dtype=int)
    n = len(y)
    if n < 150 or y.sum() < 30:
        print(f"Too little data/balance for a TRUSTWORTHY threshold (rows={n}, "
              f"winners={int(y.sum())}); need >=150 rows and >=30 winners so a "
              f"single split is not dominated by noise. Aborting.")
        return
    # load_dataset() is now time-ordered (insertion id), so this is an honest
    # forward split: train on the EARLIER 70%, test on the held-out latest 30%.
    cut = int(n * 0.7)
    clf = _new_classifier()
    clf.fit(X[:cut], y[:cut])
    proba = clf.predict_proba(X[cut:])[:, 1]
    yt = y[cut:]
    total_winners = int(yt.sum())
    print(f"Test rows: {len(yt)} | winners in test: {total_winners}")
    print(f"{'thresh':>7} {'skipped%':>9} {'winners_lost':>13} {'FNR%':>7} {'FNR_hi%':>8}")
    for thr in (0.02, 0.05, 0.10, 0.15, 0.20, 0.30):
        would_skip = proba < thr
        skipped_pct = 100.0 * would_skip.mean()
        winners_lost = int((would_skip & (yt == 1)).sum())
        fnr = 100.0 * winners_lost / total_winners if total_winners else 0.0
        fnr_hi = 100.0 * _wilson_upper(winners_lost, total_winners)
        print(f"{thr:>7.2f} {skipped_pct:>9.1f} {winners_lost:>13d} {fnr:>7.1f} {fnr_hi:>8.1f}")
    print("\nRead this as: at threshold T we skip skipped% of sims but lose FNR% of"
          " real winners. FNR_hi% is the 95% UPPER bound on that loss given the"
          " small test-winner count. Only ever enable gating at a T whose FNR_hi%"
          " (not the point estimate) is ~0 -- a 0.0 FNR on a handful of winners is"
          " noise, not safety.")


if __name__ == "__main__":
    main()