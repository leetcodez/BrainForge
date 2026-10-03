<callout icon="🎯" color="gray_bg">
	Full-codebase audit from a skeptical senior-quant-developer lens. Focus: things that **silently submit/keep bad alphas**, **corrupt state**, **overstate robustness**, or **waste the simulation budget**. Each finding has a location, why it bites, and a concrete fix.
	<br>**Audited this pass:** [orchestrator.py](http://orchestrator.py) (genetic engine + mutators), oos_[deflation.py](http://deflation.py), syntax_[validator.py](http://validator.py), llm_seed_[generator.py](http://generator.py), field_[harvester.py](http://harvester.py), db_[manager.py](http://manager.py), submit_to_[worldquant.py](http://worldquant.py), decorrelation_[selector.py](http://selector.py), surrogate_[prescreener.py](http://prescreener.py), backfill_[pnl.py](http://pnl.py), evaluate_[prescreener.py](http://prescreener.py), network_[engine.py](http://engine.py), [config.py](http://config.py).
	<br>**Caveat:** a few items reference orchestrator wiring (e.g. how `var_trials`/`num_trials` are passed into DSR, how the `fitness` column is populated) that I could only partially re-read this pass — those are tagged **\[verify\]** rather than asserted as bugs.
</callout>
**Severity:** 🔴 P0 = can submit/keep a bad alpha or corrupt data · 🟠 P1 = weakens selection or wastes the sim budget · 🟡 P2 = hygiene / divergence.
---
## 🔴 P0 — Loopholes that defeat the gates
### 1. PnL decorrelation selector silently degrades to fitness-ranking (Pass 3 ignores the budget)
In <mention-page url="https://app.notion.com/p/e7b2436dd9994dbfb4048e108c340cc9"/>, Pass 3 appends every remaining candidate **with no PnL on file** purely by impact:
```python
if returns.get(c[1]) is None:
    selected.append(c)   # no correlation check at all
```
Daily PnL only exists if you separately ran <mention-page url="https://app.notion.com/p/d2fabf7337d145599f979a566f4b0c9b"/>. On a fresh run almost nothing has stored PnL, so Pass 3 dominates and the "mutually decorrelated basket" is really just the top-N by fitness — exactly the correlated-cluster submission the module exists to prevent. Worse, <mention-page url="https://app.notion.com/p/a3de589515234786872d03216ca5606a"/> uses `select_submissions(db=db) or _diversified_order(...)`: a non-empty all-Pass-3 list is truthy, so it skips the AST-similarity fallback too — you get *neither* decorrelation method.
**Fix:** require stored PnL coverage above a threshold before trusting the selector; otherwise fall back to `_diversified_order`. At minimum, make Pass 3 respect the AST-similarity / category-cap heuristics instead of appending blind, and log loudly that N/M picks were unverified.
### 2. Submission gate treats *unmeasured* self-correlation as passing
In <mention-page url="https://app.notion.com/p/5d6ab8c24cbf468088ead5bba152fc85"/> `_get_submission_candidates`:
```sql
AND (max_correlation IS NULL OR max_correlation <= ?)
```
Any alpha whose self-correlation was never computed (the `/correlations/self` call was skipped, errored, or the row predates the check) is **eligible to submit**. The whole point of the self-correlation hard gate is bypassed by a NULL. Same NULL-permissive pattern on `failed_checks IS NULL`.
**Fix:** require `max_correlation IS NOT NULL AND max_correlation <= ?` for submission (keep NULL-permissive only for *breeding*, never for submitting). Backfill/re-measure correlation before a row is submittable.
### 3. Enrichment upsert can wipe qualification/correlation back to NULL
The `_save_alpha` upsert keeps the row when `excluded.sharpe >= COALESCE(alpha_population.sharpe, -1e18)`. That `>=` is deliberate so the batch enrichment pass (same sharpe + computed fitness/`is_qualified`/`max_correlation`) overwrites the raw save. But it also means **any later raw save of the same ****`(expression, universe, decay)`**** with an equal sharpe overwrites an already-enriched row** — resetting `is_qualified→0`, `max_correlation→NULL`, `failed_checks→''`. That can happen on resume, on a duplicate offspring before the cache warms, or if a cross-pass re-simulates. A qualified, correlation-checked alpha can quietly revert to unqualified/unchecked.
**Fix:** never regress qualification — guard the conflict so enrichment columns only move forward, e.g. `DO UPDATE ... WHERE excluded.sharpe > alpha_population.sharpe OR (excluded.sharpe = alpha_population.sharpe AND excluded.is_qualified >= alpha_population.is_qualified)`, or write enrichment via a dedicated update that never blanks a non-NULL correlation.
### 4. Live check re-fetch fails *open*
In <mention-page url="https://app.notion.com/p/a3de589515234786872d03216ca5606a"/>, `_live_failed_checks` returns `""` (treated as BRAIN-clean) on any network/parse exception, and submission proceeds. A transient blip at submit time → an alpha with genuinely failing is.checks gets POSTed. Combined with #2 (NULL `failed_checks` already passes the SQL gate), the "belt-and-suspenders" guard is defeated by one timeout.
**Fix:** fail *closed* at submission — on an indeterminate re-fetch, skip-and-retry rather than submit. Failing open is fine for breeding, not for the irreversible submit action.
---
## 🟠 P1 — Weakened selection / wasted simulations
### 5. Daily-return reconstruction misaligns across date gaps
<mention-page url="https://app.notion.com/p/e7b2436dd9994dbfb4048e108c340cc9"/> `_daily_returns` diffs consecutive *stored* rows and labels the delta with the later date:
```python
out[dates[i]] = vals[i] - vals[i - 1]
```
If a series has a missing day, that delta spans the gap (a multi-day return) but is keyed to a single date. `_pairwise_corr` then aligns two alphas on shared date keys — pairing a multi-day return on one alpha against a one-day return on another for the same label. Correlations are biased whenever the two PnL series have different gap patterns (holidays, partial backfills, late-listing names).
**Fix:** reindex both series onto a common business-day calendar, forward-difference only across adjacent calendar days, and drop (not silently span) gaps before correlating.
### 6. The validator has no type/semantic checker → garbage alphas reach live sims
<mention-page url="https://app.notion.com/p/cbc18a9b5b32468a9569db4924913693"/> checks allowed nodes, allowed operators, and **arity only**. It does not type-check operands (vector vs matrix vs boolean), nor check field existence (confirmed by the comment in <mention-page url="https://app.notion.com/p/0c1f9f6c550d4d579241b2ab59644766"/>). So crossover/mutation can graft a boolean `Compare` into a numeric slot, feed a GROUP field where a value is expected, or an LLM seed can name a non-existent field — all pass `parse_and_validate` and burn a real BRAIN simulation that errors or returns junk.
**Fix:** add a lightweight type/return-kind inference over the operator signatures in `operators.json` (each op's expected arg kinds + output kind), and validate field existence against the live catalog (`data_fields.json`) before simulating. This is probably the single biggest sim-budget leak.
### 7. `mutate()` falls back to the unchanged parent
In the genetic engine, if 4 attempts fail to produce a valid, non-tautological, motif-allowed mutant, `mutate()` returns the **parent expression verbatim**. Those duplicates collide with `UNIQUE(expression,universe,decay)` / the cache and are dropped, so the *effective* offspring count per generation is below target — the search quietly under-explores and leans harder on elites, accelerating convergence/stagnation.
**Fix:** count fallback rate; if a parent can't be mutated, draw a fresh seed from the grammar engine instead of returning the parent, and track "mutation yield" as a health metric.
### 8. Cross-universe variants are exempted from the similarity filter, then submitted as a basket
`_diversified_order` in <mention-page url="https://app.notion.com/p/a3de589515234786872d03216ca5606a"/> intentionally skips the AST-similarity check for same-expression / different-universe variants (the "universe funnel"). But the same expression on TOP3000 vs TOP1000 vs TOP500 is usually **highly return-correlated**, not "lightly decorrelated." You can spend several of your `MAX_SUBMISSIONS_PER_RUN=10` slots on near-twins that BRAIN then rejects for self-correlation.
**Fix:** treat universe variants as one logical candidate — submit only the best-fitness universe unless realized pairwise PnL correlation (not an assumption) shows the variants are actually decorrelated.
### 9. Derived-sim fan-out is unbounded relative to the semaphore (the "stuck generation")
Each generation spawns base offspring **plus** refinement (`REFINE_MAX_BRANCHES=24`, `REFINE_MAX_TARGETS_PER_GEN=6`), a universe sweep over 4 universes, and negation harvests (`NEGATION_MAX_PER_GEN=8`, resume `=12`) — all funneling through `MAX_CONCURRENT_SIMULATIONS=3` with 429 backoff. A single generation can balloon into many hundreds of simulations at 3-wide, which reads as "gen 0/1 piling up and never advancing." The checkpoint only advances at the *end* of the `for gen` body, so a generation that never drains re-enters forever.
**Fix:** bound total derived sims per generation with an explicit budget (sum of all fan-out paths), and/or raise concurrency. Make "sims this generation" observable so a runaway generation is visible.
### 10. Deflated-Sharpe inputs are fragile and the benchmark grows with run length \[verify\]
<mention-page url="https://app.notion.com/p/87b025184bb6436792ce61f96a8dd38f"/> is unit-correct now, but its output depends entirely on two caller-supplied quantities: `num_trials` (capped by `DEFLATION_MAX_TRIALS`) and `var_trials` (must be the variance of **per-period** trial Sharpes). If the orchestrator passes the variance of *annualized* sharpes, or a constant, the expected-max-Sharpe hurdle `sr0` is wrong and DSR is meaningless. Even correct, `num_trials = count_trials()` grows every generation, so the hurdle ratchets up over a long run and late-discovered alphas are penalized for *when* they were found.
**Fix:** assert/log the exact `var_trials` definition at the call site; compute it from per-period trial Sharpes only. Confirm `DEFLATION_MAX_TRIALS` is set so the hurdle doesn't creep.
### 11. No true out-of-sample holdout anywhere
The pipeline optimizes IS fitness, then `overfitting_risk_multiplier` and `estimate_pbo` lean on BRAIN's fixed IS/OOS split — there is no independent holdout the engine controls, and PBO is explicitly an approximation that's *logged, never gated*. The system markets OOS robustness but selection is still IS-greedy with a statistical haircut. That's the classic factory-overfitting setup.
**Fix:** carve a true time holdout (e.g. reserve the most recent N months, never used for promotion) and gate on its degradation; or at minimum promote on a blend of DSR + realized OOS, and make PBO an actual soft gate.
### 12. `coverageMode` conflates temporal and cross-sectional sparsity
<mention-page url="https://app.notion.com/p/2a4b873906d649ea8592bba4ff790c9e"/> sets `coverageMode = "direct" if cov >= HIGH_COVERAGE(0.60) else "backfill"` purely on coverage magnitude, then wraps backfill fields in `ts_backfill(..., 252)`. The code's own comment warns backfill only fixes *temporal* sparsity (stale-but-valid between events), not *cross-sectional* gaps (names that never have data). A low-coverage field that's cross-sectionally sparse gets a year-long backfill anyway → stale, fabricated-looking signal across names that should be NaN.
**Fix:** distinguish event-sparse (low temporal density, high name coverage) from name-sparse fields using per-name vs per-day coverage if the API exposes it; only backfill the former.
---
## 🟠 P1 — Specific to evaluate_[prescreener.py](http://prescreener.py) (your open file)
### 13. The "time-ordered split" is not actually time-ordered
<mention-page url="https://app.notion.com/p/10525b3e833f497590d911e9ca2d3fbe"/> does `cut = int(n*0.7)` and trains on `X[:cut]`, testing on the tail — but `X, y` come from `load_dataset()` → `db.load_history_sync()`, whose query has **no ****`ORDER BY`**:
```sql
SELECT expression, universe, decay, sharpe, ... FROM alpha_population WHERE sharpe IS NOT NULL
```
Row order is engine/rowid order, and the `ON CONFLICT` upserts mutate rows in place (timestamp updates, rowid doesn't). So the split is effectively arbitrary, not chronological — the FNR/skip% table you'd use to choose a gating threshold doesn't measure true forward generalization, which is the entire purpose of the script.
**Fix:** add `ORDER BY timestamp ASC` (or a dedicated `created_at`) to the history query used for evaluation, and split on that. Better: walk-forward CV across several cut points rather than a single 70/30.
### 14. Single-split threshold selection is unstable on this data scale
The guard is `n >= 80` and `winners >= 10`. Picking a skip threshold off one split with \~10 positives will swing wildly run-to-run; an FNR of "0%" on a dozen winners is noise.
**Fix:** require more positives before trusting a threshold, report a confidence interval on FNR, and only ever enable gating at a threshold whose FNR upper bound (not point estimate) is \~0.
---
## 🟡 P2 — Divergence & hygiene
- **Breeding pool thresholds are hardcoded and diverge from config.** <mention-page url="https://app.notion.com/p/5d6ab8c24cbf468088ead5bba152fc85"/> `_get_top_population` filters `sharpe > 0.5 AND turnover < 0.8`, unrelated to `MIN_SHARPE=1.25` / `MAX_TURNOVER=0.70`. Intentional (breed from a wider pool) but the magic numbers should live in config, and `turnover < 0.8` vs the `0.70` gate is an easy footgun. Also `ORDER BY fitness DESC` mixes NULL-fitness raw rows into parent selection.
- **Enrichment isn't transactional.** `isolation_level=None` (autocommit) means a generation's enrichment is a sequence of independent commits; an interruption mid-enrichment leaves a half-qualified generation (the mid-gen checkpoint mitigates resume, not the partial-commit state itself).
- **Surrogate label is an IS-winner flag.** <mention-page url="https://app.notion.com/p/ebf3b896018a4d398b62627ee3f57faf"/> `_is_winner` uses IS sharpe/turnover from the same population it scores; fine while SHADOW-only, but it predicts "looked good IS," not "survived OOS" — don't promote it to a gate on that label. Also `config.field_family` can return families outside `_FAMILIES`, silently dropping those counts from features.
- **`_mutate_gate_turnover`**** injects an economically arbitrary regime gate** (`trade_when(ts_zscore(random_field, w) > 0, signal, -1)`) unrelated to the signal — useful as a turnover lever, but it manufactures alphas whose conditioning has no thesis. Fine for exploration; don't let these dominate submissions.
- **`_data_category`**** / experience-memory field matching uses ****`\bfield\b`**** regex over expression text** and won't see fields inside compound tokens like `vec_avg(x)`; category attribution and failure penalties are approximate.
---
## Fix-first order
<table fit-page-width="true" header-row="true">
<tr>
<td>#</td>
<td>Fix</td>
<td>Why first</td>
</tr>
<tr>
<td>2</td>
<td>Require non-NULL self-correlation to submit</td>
<td>One-line SQL; closes a real submit loophole</td>
</tr>
<tr>
<td>4</td>
<td>Fail closed in `_live_failed_checks`</td>
<td>One blip currently submits a flagged alpha</td>
</tr>
<tr>
<td>1</td>
<td>Don't let Pass 3 bypass the correlation budget</td>
<td>Selector is a no-op without PnL coverage</td>
</tr>
<tr>
<td>3</td>
<td>Stop enrichment upsert from blanking qualification</td>
<td>Silent state corruption on resume/dupes</td>
</tr>
<tr>
<td>6</td>
<td>Type + field-existence validation</td>
<td>Biggest sim-budget leak</td>
</tr>
<tr>
<td>13</td>
<td>`ORDER BY timestamp` before the prescreener split</td>
<td>Makes the eval you're looking at actually valid</td>
</tr>
</table>
<callout icon="📌" color="yellow_bg">
	This is a Notion mirror — none of these are committed. Tell me which to turn into concrete patches and I'll write the exact diffs against the relevant file pages for you to copy into `leetcodez/BrainForge`.
</callout>
<empty-block/>