# Integration Acceptance Report — BrainForge v2 Baseline

**Execution Mode:** `FORGE2_OFFLINE_ONLY=1`  
**Date:** 2026-10-03  
**Audited Campaign Database:** `brain_memory.earnings4_run2.db` (59 MB, 2,432 alphas, 706,992 PnL rows)  
**Catalog Baseline:** `src/brain_fields_merged.json` (122,748 fields, 89 MB)  
**Test & Verification Status:** 136/136 tests passed, 10,000/10,000 fuzz checks passed, 54/54 smoke checks passed  

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

### 2.2 Regime & Metadata Attribution
* **Universes in Database:**
  * `TOP3000`: 1,857 candidates (99.7%)
  * `TOP200`: 2 candidates
  * `TOP1000`: 2 candidates
  * `TOP500`: 2 candidates
* **Region & Delay:**
  * In the v1 database schema, `region` and `delay` were ambient script settings and were **not recorded as database columns**.
  * When evaluated as a raw un-migrated database, `forge2_quant_review.py` treats region/delay as unknown (`[file_path, None, universe]`), preventing cross-campaign pooling.
  * When migrated with explicit axes (`USA`, `delay=1`), candidates resolve cleanly into their true `['USA', 1, 'TOP3000']` regime.

### 2.3 Redundancy, Clones & Basket Redundancy
A full pairwise correlation analysis on the 572 daily PnL increment series (163,306 distinct candidate pairs) revealed **severe collinearity and family crowding**:

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
* **Single-Dataset Crowding Rejections:** **537 candidates** were rejected immediately for `dataset_budget` because 100% of the alphas in this run belonged to the `earnings4` dataset, exceeding the 40% family cap.
* **Return Redundancy Rejections:** **26 candidates** were rejected for `absolute_return_redundancy` ($\|r\| > 0.80$).
* **Effective Core Candidates Admitted:** Only **8 verified diverse candidates** could be admitted under portfolio constraints from the entire 2,432-alpha pool.

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
* **Source Database Preserved:** Source SHA-256 hash verified identical before and after (`b8d0c667...`).
* **Rescored Rows:** 2,432 rows rescored under policy `forge2-v4-quant-research-eb0a7552fa782e0d-third1`.
* **Missing Check Handling:** 2,432 rows had missing sub-check payloads. These were **explicitly marked `unknown_check_rows: 2432` and labeled `CHECKS_UNVERIFIABLE`**, rather than silently coerced to `0` or passed.
* **Trial Accounting:** Preserved `uncapped_recorded_trials: 2432` so Deflated Sharpe Ratio (DSR) multiple-testing penalties are maintained.
* **Warmstart Candidates:** 18 diverse elite warmstart candidates identified and exported to `checkpoint.json`.

---

## 4. Decision Matrix: Next Upgrade Steps

Based on the audit evidence, the state of the project aligns with the following decision criteria:

| Observed Evidence | Audit Reality | Required Action |
| :--- | :--- | :--- |
| **Missing PnL / Regime Metadata** | 69.3% of alphas lack daily PnL; region/delay not stored in v1 schema. | **Action 1:** Standardize archive ingestion to always write `forge2_epoch_manifest.json` and `forge2_field_meta.json`. |
| **Strong Basket Redundancy** | 10.2% of candidate pairs have $\|r\| > 0.80$; 537 alphas exceed dataset cap. | **Action 2:** Break single-dataset confinement; activate multi-dataset seeding from `src/brain_fields_merged.json` with strict offline basket decorrelation. |
| **Only Cumulative PnL** | Dollar PnL only; zero capital normalization or portfolio cash accounts. | **Action 3:** Keep return analysis at the standardized PnL redundancy level; do NOT attempt unverified HAC Sharpe or alpha capital weighting. |
| **Recovery Incompatibilities** | Raw v1 databases fail policy guards. | **Action 4:** Require one-shot offline migration (`forge2_migrate_offline.py`) before attempting warmstart or replay. |

---

## 5. Unresolved Risks & Non-Goals

1. **Do NOT Start RL or Complex Surrogates Yet:**  
   Without capital-normalized return series and with 69.3% missing PnL rows, predictive surrogate models trained on legacy data would learn biased representations of factor crowding rather than true market anomalies.
2. **Do NOT Re-Query Remote Platform for Historical Checks:**  
   Missing sub-checks in legacy runs must remain labeled `CHECKS_UNVERIFIABLE`. Historical records are audit evidence, not an authorization to poll remote endpoints.
3. **Multi-Dataset Seed Pool is Mandatory for Run 5:**  
   Continuing single-dataset campaigns (`WQ_DATASET_ID=earnings4`) is mathematically exhausted—it hits the 40% dataset budget cap within 8 selections. Run 5 must draw from the 122,748-field multi-dataset catalog.

---

## 6. Actionable Next Steps

1. **Step 1 (Immediate):** Use `migrated_runs/earnings4_run2` as the verified historical benchmark rather than un-migrated raw files.
2. **Step 2:** Formulate Run 5 campaign configuration targeting multi-dataset factor exploration across `USA` and `EUR` universes using `src/forge2_campaign.py`.
3. **Step 3:** Enable offline basket diversity checks (`BASKET_SELECTION_ENABLED=1`) during the genetic selection loop to eliminate the 10.2% collinear clone problem before simulation dispatch.
