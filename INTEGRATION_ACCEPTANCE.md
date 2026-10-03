# Integration Acceptance Report — BrainForge v2 Baseline

**Execution Mode:** `FORGE2_OFFLINE_ONLY=1`
**Date:** 2026-10-03
**Audited Campaign Database:** `brain_memory.earnings4_run2.db` (59 MB, 2,432 alphas, 706,992 PnL rows)
**Catalog Baseline:** `src/brain_fields_merged.json` (122,748 fields, 89 MB)
**Test & Verification Status:** 136/136 tests passed, 10,000/10,000 fuzz checks passed, 54/54 smoke checks passed

> [!IMPORTANT]
> **Revision note (2026-10-03):** This report has been corrected to separate observed
> facts, migration assumptions, and policy-imposed limits. Earlier language
> claiming "mathematical exhaustion," "true regime," and a mandatory Run 5
> recommendation has been removed per the user's factual review.

---

## 1. Executive Summary & Baseline Lockdown

All core v2 components from the clean handoff package have been integrated into the local workspace (`src/`, `tests/`, `docs/`, `scripts/`, `evidence/`, `tools/`). Prior local flat code, databases, session files, and checkpoints have been backed up into `backups/pre_v2_baseline/`.

### Verified Assets & Hashes
* **Package Manifest:** `FULL_PROJECT_MANIFEST.json` verified (`169` packaged file hashes certified by `scripts/verify_manifest.py`).
* **Environment Integrity:** `FORGE2_OFFLINE_ONLY=1` enforced globally. Zero network calls or external probes occurred.
* **Test Suite:** `136 passed, 0 failed in 20.25s` via pytest.
* **AST Genetics Fuzzing:** `5,000` iterations, `10,000` AST outputs validated, `0` syntax or type errors.
* **Replay Smoke Test:** `54/54` checks passed across USA and EUR delay grids against `src/brain_fields_merged.json`.
* **Git Checkpoint:** Local commit created on `main` (commit message locked down; zero automatic pushes/deployments).

---

## 2. Audit of Existing Campaign Database (`earnings4_run2`)

We audited `brain_memory.earnings4_run2.db` using the read-only quantitative reviewer (`src/forge2_quant_review.py`) on an immutable backup copy.

### 2.1 Candidate Inventory & Usable Recorded PnL
* **Total Stored Population:** 2,432 alpha candidates.
* **Scored Candidates (Finite Sharpe & Fitness):** 1,863 alphas.
* **Candidates with Recorded PnL:** **572 alphas** (23.5% of total population, 30.7% of scored population).
* **Missing PnL:** **1,291 scored alphas** (69.3%) have zero recorded daily PnL rows in `alpha_pnl`.
* **Trading Calendar Coverage:**
  * Alphas with PnL share an identical **1,236-day synchronized trading calendar** from `2019-01-02` to `2023-12-29`.
  * Common overlap across all 572 PnL-enabled candidates is **100% (1,236 days)**, well exceeding the 60-day minimum overlap threshold.

> [!NOTE]
> **PnL collection bias:** All 572 PnL-covered rows have `is_qualified=1`; zero
> non-qualified rows have PnL. PnL was collected only for candidates that
> passed an earlier qualification gate. The PnL-covered subset is a biased
> sample of the full search. Basket correlation/redundancy analysis applies
> only to this subset and cannot characterize unseen candidates.

### 2.2 Regime & Metadata Attribution
* **Universes in Database:**
  * `TOP3000`: 1,857 candidates (99.7%)
  * `TOP200`: 2 candidates
  * `TOP1000`: 2 candidates
  * `TOP500`: 2 candidates
* **Region & Delay:**
  * In the v1 database schema, `region` and `delay` were ambient script settings and were **not recorded as database columns**.
  * The legacy `config.py` contains `DEFAULT_REGION = "USA"` and `DEFAULT_DELAY = 1`. The `.env` file has no `WQ_REGION` or `WQ_DELAY` override. Available run logs (`ern4_overnight.log`) do not record which `region`/`delay` were active at simulation time.
  * **These defaults are consistent with USA/delay-1 but are not verified provenance.** No original run log, checkpoint, or snapshot explicitly confirms the region and delay used for each submitted simulation. The `.wq_checkpoint.earnings4_run2.json` contains only `{generation, submission_count, timestamp}` with no regime axes.
  * When migrated with explicit axes (`USA`, `delay=1`), the migration labels candidates with an assumed `['USA', 1, 'TOP3000']` regime. **This is a migration assumption, not a recovered historical fact.**

### 2.3 Redundancy, Clones & Basket Redundancy
A full pairwise correlation analysis on the 572 daily PnL increment series (163,306 distinct candidate pairs) revealed **significant collinearity and family crowding**:

| Metric | Count | Percentage |
| :--- | :--- | :--- |
| **Scored Candidates Evaluated** | 1,863 | 100.0% |
| **Exact Expression Duplicates** | 116 | 6.2% |
| **Exact Sign Flips (`-expr` vs `expr`)** | 3 | 0.2% |
| **Pairwise Comparisons (PnL)** | 163,306 | 100.0% |
| **Pairs with $\|r\| > 0.80$** | 16,584 | **10.2%** |
| **Pairs with $\|r\| > 0.90$** | 4,477 | **2.7%** |
| **Virtual Clones ($\|r\| > 0.99$)** | 246 | **0.15%** |

#### Basket Selection Rejections (Ledoit-Wolf Shrunk Residuals):
When the v2 basket selection algorithm (`select_basket` with size=20, max correlation=0.80, dataset cap=40%) was applied to the scored `TOP3000` population:
* **Dataset-Cap Rejections:** **537 candidates** were rejected for `dataset_budget` because 100% of the alphas in this run belong to the `earnings4` dataset, exceeding the 40% family cap (max 8 from any one dataset in a 20-member basket).
* **Return Redundancy Rejections:** **26 candidates** were rejected for `absolute_return_redundancy` ($\|r\| > 0.80$).
* **Effective Core Candidates Admitted:** Only **8 verified diverse candidates** were admitted under portfolio constraints from the entire 2,432-alpha pool.

> [!IMPORTANT]
> **The eight-candidate ceiling is imposed by policy, not by the data.**
> A 20-member basket with a 40% dataset cap permits at most 8 candidates
> from `earnings4`. Hitting this ceiling does not prove the dataset is
> "exhausted." The rejection count also depends on selection order:
> dataset-budget checks occur before correlation checks, so many candidates
> rejected for `dataset_budget` were never evaluated for PnL redundancy.
> See the [Selection Policy Ablation](#appendix-selection-policy-ablation)
> for a controlled comparison separating these effects.

---

## 3. Local Recovery & Compatibility Analysis

### 3.1 Policy & Epoch Incompatibility (Fail-Closed Behavior)
* **Direct Runner Execution:** If `forge2_factory` or `orchestrator` is pointed directly at an un-migrated v1 database, execution is rejected by `forge2_policy.guard`:
  ```text
  ValueError: Effective policy/operator/settings changed or unverified: preserve DB and migrate offline
  ```
* **Safety Benefit:** This fail-closed design prevents silent overwrites, accidental credential use, or mixing alphas generated under different policy regimes.

### 3.2 Offline Migration Validation (`src/forge2_migrate_offline.py`)
We executed an offline migration of `earnings4_run2` into `migrated_runs/earnings4_run2/`:
* **Source Database Preserved:** Source SHA-256 hash verified identical before and after.
* **Rescored Rows:** 2,432 rows rescored under policy `forge2-v4-quant-research-eb0a7552fa782e0d-third1`.
* **Missing Check Handling:** 2,432 rows had missing sub-check payloads. These were **explicitly marked `unknown_check_rows: 2432` and labeled `CHECKS_UNVERIFIABLE`**, rather than silently coerced to `0` or passed.
* **Warmstart Candidates:** 18 candidates exported to `checkpoint.json` as the top NSGA-II-rescored population.

> [!WARNING]
> **Migration does not recover unknown provenance.** Supplying `USA` and
> `delay=1` labels a migrated scoring view. Those axes become verified
> historical facts only if original configuration, logs, or snapshots support
> them. Migration defaults are not proof.
>
> **Warmstart seeds are not certified diverse or submission-ready.** The 18
> seeds are the top-ranked by NSGA-II fitness after rescoring. They were NOT
> passed through `select_basket()`. Zero of the 18 have recorded PnL; zero
> have `is_qualified=1` in the original database. They should remain
> historical research candidates.

### 3.3 Recorded-Trial Limitations
* **Preserved rows:** 2,432 is useful accounting, but does not establish the total attempted search. Failed simulations, duplicates rejected pre-submission, and manual experiments are not tracked in `alpha_population`.
* **DSR calibration:** Deflated Sharpe Ratio penalties computed on this count underestimate the true multiple-testing burden.

---

## 4. Decision Matrix: Next Upgrade Steps

Based on the audit evidence, the state of the project aligns with the following decision criteria:

| Observed Evidence | Audit Reality | Required Action |
| :--- | :--- | :--- |
| **Missing PnL / Regime Metadata** | 69.3% of alphas lack daily PnL; region/delay not stored in v1 schema. PnL collection is correlated with `is_qualified`. | Standardize archive ingestion. Investigate existing archives for recoverable PnL and original axis settings. Do not extrapolate from the PnL-covered subset. |
| **Basket Policy vs. Redundancy** | 537 candidates rejected by dataset-cap policy; 129 rejected by actual PnL redundancy when cap removed (see ablation §C). | Run the fixed-pool ablation to determine whether the selector removes genuinely redundant candidates or mostly enforces a multi-dataset policy on a single-dataset archive. |
| **Only Cumulative PnL** | Dollar PnL only; zero capital normalization or portfolio cash accounts. | Keep return analysis at the standardized PnL redundancy level; do NOT attempt unverified HAC Sharpe or alpha capital weighting. |
| **Recovery Incompatibilities** | Raw v1 databases fail policy guards. | Require one-shot offline migration before warmstart or replay. |

---

## 5. Unresolved Risks & Limitations

1. **Do NOT Start RL or Complex Surrogates Yet:**
   Without capital-normalized return series and with 69.3% missing PnL rows, predictive surrogate models trained on legacy data would learn biased representations. These need trustworthy labels and evaluation evidence first.
2. **Do NOT Re-Query Remote Platform for Historical Checks:**
   Missing sub-checks in legacy runs must remain labeled `CHECKS_UNVERIFIABLE`. Historical records are audit evidence, not an authorization to poll remote endpoints.
3. **Multi-Dataset Seeding Is an Exploration Option, Not a Demonstrated Remedy:**
   We can build valid expressions from the full 122,748-field catalog, but expressions without recorded PnL have unverified diversification. Broader seeding does not guarantee decorrelated results until candidates are simulated and evaluated.
4. **PnL-Covered Subset May Be Selectively Collected:**
   The PnL-covered pool (572 of 1,857 scored) consists exclusively of `is_qualified=1` candidates. This selection bias means the measured redundancy, correlation structure, and diversity metrics describe the qualified tail, not the full attempted search.

---

## Appendix: Selection Policy Ablation

See `evidence/selection-ablation-results.json` for full machine-readable output and `evidence/SELECTION_POLICY_AUDIT.md` for the detailed analysis.

**Summary of the four fixed-pool variants (TOP3000, basket size=20):**

| Variant | Selected | Verified | Rejection Breakdown | Mean Abs Corr | Max Abs Corr |
| :--- | :--- | :--- | :--- | :--- | :--- |
| A: No controls | 20 | — | — | 0.796 | 1.000 |
| B: Dedup only | 20 | — | — | 0.796 | 1.000 |
| C: PnL controls, no cap | 20 | 16 | 129 abs-redundancy | 0.596 | 0.794 |
| D: PnL controls + cap | 12 | 8 | 428 dataset-budget, 71 abs-redundancy | 0.625 | 0.794 |

**Key finding:** The dataset cap is the primary binding constraint, not PnL redundancy.
Variant C selects 20 candidates (16 verified + 4 exploration) from the same single-dataset
pool by removing only those with measured PnL redundancy. Variant D caps at 12 (8 + 4)
because the dataset-budget check fires first and blocks 428 candidates that were never
evaluated for correlation. 12 candidates accepted by C are absent from D — these were
rejected solely due to the dataset cap, not because they were PnL-redundant.
