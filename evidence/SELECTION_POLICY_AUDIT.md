# Selection Policy Audit — Offline Ablation Report

**Campaign:** `earnings4_run2`
**Source DB:** `backups/pre_v2_baseline/brain_memory.earnings4_run2.db` (read-only)
**Field Metadata:** `migrated_runs/earnings4_run2/.epochs/c8336ac56f924355bf715f66b8e0157c/forge2_field_meta.json`
**Machine-Readable Output:** `evidence/selection-ablation-results.json`
**Date:** 2026-10-03
**Mode:** `FORGE2_OFFLINE_ONLY=1`; zero network calls, zero platform authentication

---

## 1. Core Question

> Is the current selector removing genuinely redundant candidates, or mostly
> enforcing a multi-dataset policy on a deliberately single-dataset archive?

**Answer: The dataset cap is the dominant binding constraint.** When the cap is
removed (Variant C), `select_basket()` fills a 20-member basket from the same
single-dataset pool using only PnL correlation and Ledoit-Wolf residual checks.
When the cap is active (Variant D), only 12 seats are filled because the
dataset-budget check fires first and blocks 428 candidates before they are ever
evaluated for PnL redundancy.

---

## 2. Fixed-Pool Description

All four variants operate on the **same candidate pool** with **fixed thresholds**:

| Parameter | Value |
| :--- | :--- |
| Scored candidates (TOP3000) | 1,857 |
| Unique expressions (after dedup) | 1,747 |
| Exact duplicates removed | 110 |
| With recorded PnL | 571 (30.7%) |
| Common trading days | 1,236 (2019-01-02 to 2023-12-29) |
| Basket size | 20 |
| Max abs correlation | 0.80 |
| Min residual fraction | 0.10 |
| Explore fraction | 0.20 (4 seats) |

**Regime attribution:** `region=USA`, `delay=1` are from legacy `config.py`
defaults (`DEFAULT_REGION`, `DEFAULT_DELAY`). These are **consistent assumptions**,
not verified provenance from original run logs or checkpoints. See §6.

---

## 3. Ablation Results

### Variant A — No Controls (Raw Fitness Ranking)
* **Selected:** 20
* **PnL-covered in selection:** 10 (50%)
* **Mean abs correlation:** 0.796
* **Max abs correlation:** 1.000 (identical/near-identical PnL series)
* **Pairs above 0.80:** 26 of 45

The top-20 by raw fitness contains extreme PnL redundancy, including near-clone
pairs (|r| = 1.0). Half the selected candidates have no recorded PnL at all.

### Variant B — Expression Deduplication Only
* **Selected:** 20
* **PnL-covered:** 10 (50%)
* **Mean abs correlation:** 0.796
* **Max abs correlation:** 1.000
* **Pairs above 0.80:** 26 of 45

Deduplication removes 110 exact expression duplicates from the pool but does not
change the top-20 selection — the duplicates had lower fitness and didn't appear
in the top 20 anyway. PnL redundancy is identical to Variant A.

### Variant C — PnL Controls, Dataset Cap Disabled
* **Selected:** 20 (16 verified + 4 exploration)
* **PnL-covered:** 16 (80%)
* **Mean abs correlation:** 0.596
* **Max abs correlation:** 0.794
* **Pairs above 0.80:** 0
* **Rejections:** 129 for `absolute_return_redundancy`
* **Shrinkage (Ledoit-Wolf):** captured in JSON output
* **Datasets in basket:** `['earnings4']` (all single-dataset, as expected)

With the dataset cap disabled, the PnL correlation and residual controls alone
select 20 candidates with no pair exceeding the 0.80 threshold. Mean pairwise
abs correlation drops from 0.796 (Variant A) to 0.596. 129 candidates were
rejected for measured PnL redundancy — this is the genuine redundancy removed by
the selector's quantitative controls.

### Variant D — PnL Controls + Current Dataset Cap
* **Selected:** 12 (8 verified + 4 exploration)
* **PnL-covered:** 8 (67%)
* **Mean abs correlation:** 0.625
* **Max abs correlation:** 0.794
* **Pairs above 0.80:** 0
* **Rejections:** 428 for `dataset_budget`, 71 for `absolute_return_redundancy`
* **Datasets in basket:** `['earnings4']`

The 40% dataset cap fires first in the selection loop. After 8 verified candidates
from `earnings4` are admitted, every remaining `earnings4` candidate is blocked by
`dataset_budget` regardless of PnL characteristics. The exploration reserve adds 4
more seats (also `earnings4`), reaching 12 total. The remaining 8 seats cannot be
filled from this single-dataset archive.

---

## 4. Cross-Variant Comparison

| Comparison | Overlap Count |
| :--- | :--- |
| A ∩ B | 20 (identical) |
| A ∩ C | 6 |
| A ∩ D | 2 |
| B ∩ C | 6 |
| B ∩ D | 2 |
| C ∩ D | 8 |

* **C minus D (12 candidates):** These 12 candidates passed all PnL correlation
  and residual checks but were rejected solely by the dataset cap. They are
  demonstrably non-redundant by measured PnL evidence.
* **D minus C (4 candidates):** These 4 appear in D's exploration reserve but not
  in C, because C's verified core already filled all 16 verified seats with
  different PnL-diverse candidates, pushing these to different exploration
  positions.

> [!IMPORTANT]
> The 12 candidates in C − D are the clearest evidence that the dataset cap,
> not PnL redundancy, is the binding constraint on this archive. The selector's
> quantitative controls (correlation + residual) can fill a 20-member basket
> from a single dataset without any pair exceeding |r| = 0.80.

---

## 5. Warmstart Assessment

The migration exported 18 "warmstart" seeds to `checkpoint.json`:

| Property | Value |
| :--- | :--- |
| Total warmstart seeds | 18 |
| Matched to scored population | 14 |
| With recorded PnL | **0** |
| With `is_qualified=1` | **0** |
| Present in Variant C basket | **0** |
| Present in Variant D basket | 4 (exploration slots only) |

**Construction method:** The warmstart is the top-N population ranked by
NSGA-II-rescored fitness. It did **not** pass through `select_basket()`.

**Status:** Historical research candidates. None have PnL evidence for
redundancy evaluation. None were qualified in the original database. They should
not be labeled as qualified, independently diverse, or submission-ready.

The 4 warmstart seeds that appear in Variant D's basket (`88LGYqv7`, `O097qPWJ`,
`P01PAnKM`, `QPQ7lQrp`) occupy exploration reserve slots — they were admitted
because they were not yet rejected for `dataset_budget` or correlation, but they
have no PnL evidence to verify their diversity.

---

## 6. Regime Provenance Verification

### What was found:
| Artifact | region | delay | Status |
| :--- | :--- | :--- | :--- |
| Legacy `config.py` L1113-1114 | `DEFAULT_REGION = "USA"` | `DEFAULT_DELAY = 1` | **Consistent default** |
| `.env` | No `WQ_REGION` | No `WQ_DELAY` | No override present |
| `.wq_checkpoint.earnings4_run2.json` | Not stored | Not stored | No evidence |
| `ern4_overnight.log` | No region/delay entries | — | No evidence |
| Database `alpha_population` schema | No `region` column | No `delay` column (uses per-candidate `decay`) | Not recorded |
| Migration `forge2_field_meta.json` | `USA` | `1` | **Migration parameter, not recovery** |

### Conclusion:
The legacy code used `DEFAULT_REGION="USA"` and `DEFAULT_DELAY=1` with no evidence
of any override. The `build_settings()` function at L1206-1221 of legacy `config.py`
hardcodes these defaults into every simulation payload. The `.env` contains no
`WQ_REGION` or `WQ_DELAY` variable.

**Strength of evidence: CONSISTENT BUT CIRCUMSTANTIAL.** The defaults are the most
likely values used, but no individual simulation response or submission record
confirms the actual region/delay sent to the platform. We should label these as
"consistent defaults from legacy config" rather than "verified historical regime."

---

## 7. Missing-Evidence Bias

| Metric | Value |
| :--- | :--- |
| Total scored (TOP3000) | 1,857 |
| With PnL | 571 (30.7%) |
| Without PnL | 1,286 (69.3%) |
| PnL coverage | **Perfectly correlated with `is_qualified=1`** |
| Median fitness (PnL-covered) | 0.00266 |
| Median fitness (all scored) | −0.01465 |

PnL was collected exclusively for candidates that passed a qualification gate.
The PnL-covered pool is the right tail of the fitness distribution. This means:

* **Correlation analysis covers only the qualified tail.** The 10.2% high-correlation
  rate among PnL-covered pairs may understate or overstate the redundancy in the
  full pool — we cannot know without PnL for non-qualified candidates.
* **Basket selection cannot evaluate unseen candidates.** The 1,286 candidates
  without PnL pass through basket selection only as exploration reserve entries,
  never as verified core members.
* **Do not extrapolate** the PnL-covered subset's correlation structure to the
  full scored population.

### Recorded-Trial Limitations

The database contains 1,857 scored rows (TOP3000). This is **not** the total
number of attempted simulations:

* Failed simulations are not recorded in `alpha_population`.
* Pre-submission duplicate filtering may have discarded candidates before
  simulation.
* Manual test expressions may have been simulated without recording.

DSR penalties computed on 1,857 (or 2,432 total) underestimate the true
multiple-testing burden. The effective independent trial count is unknown.

---

## 8. Conclusions

1. **The dataset cap is the primary binding constraint,** not PnL redundancy.
   Removing it lets the selector fill all 20 seats with measured-diverse
   candidates (max |r| = 0.794, mean |r| = 0.596).

2. **Genuine PnL redundancy is moderate.** 129 candidates are rejected by
   correlation/residual checks when the dataset cap is removed — this represents
   real redundancy in the PnL-covered pool.

3. **The warmstart is not independently diverse.** Zero of 18 seeds have PnL,
   zero are qualified, and zero appear in Variant C's PnL-verified basket.

4. **Regime attribution is consistent but not verified.** `USA`/`delay=1` are
   the most likely values, supported by legacy `config.py` defaults and absence
   of overrides, but no simulation response or submission log confirms them.

5. **Missing-evidence bias is severe.** Only 30.7% of scored candidates have
   PnL, all from the qualified tail. The measured redundancy structure may not
   represent the full search.

---

## 9. Recommended Next Actions

> [!CAUTION]
> These are evidence-led recommendations, not prescriptions. Each requires
> the user's decision before proceeding.

1. **Decide whether the dataset cap serves the current research goal.**
   If the campaign will remain single-dataset (earnings4), the 40% cap
   artificially limits selection to 8 verified candidates. The cap's purpose
   is multi-dataset diversification, which requires multi-dataset generation.

2. **Investigate recoverable evidence locally.** Search existing archives,
   snapshot directories, and log files for additional PnL data, raw check
   payloads, or original axis settings. Do not backfill from remote sources.

3. **If expanding to multi-dataset seeding:** expressions without recorded
   PnL have unverified diversification. Broader seeding is an exploration
   option — evaluate results after simulation, not before.

4. **Fix the warmstart before using it.** The 18 seeds lack PnL and
   qualification. If used as an initial population, they should be treated as
   untested hypotheses requiring fresh evaluation.

5. **Do not start RL, surrogates, or broader search** until evaluation
   labels (PnL, checks) are trustworthy and the selection policy question is
   resolved.
