<callout icon="🎯" color="blue_bg">
	**Purpose:** A read-only post-mortem layer that mines the population DB (`alpha_population` + `alpha_pnl` + expression ASTs) and tells us *quantitatively* what went wrong in a run — correlation, monoculture, operator under-use, overfit, and GA search failure — so the next run can be fixed against numbers, not vibes.
	**Scope discipline:** This system **describes, it does not fix**. It's a standalone side-script (`run_diagnostics.py`) like `analyze_run.py` / `backfill_pnl.py` — it never touches the orchestrator, the schema, or live runs. It only reads, and writes its own metrics table/JSON.
</callout>
## The core insight from the research
Two findings should shape the whole design:
1. **Syntactic diversity ≠ behavioral diversity.** Counting operators tells you what the *code* looks like, not what the *strategy* does. The genetic-programming literature is explicit that semantic (output-behavior) diversity is what matters and is routinely high-syntactic / low-behavioral. So we measure *both*, and treat the **PnL-based** behavioral metrics as the source of truth.
2. **"How correlated are we, really?" has a single best answer: the Effective Number of Bets (ENB).** From the eigenvalues of the alpha return-correlation matrix (Meucci). It collapses a 572×572 correlation matrix into one honest number: *how many genuinely independent bets do we actually have?* For this run I expect it to be embarrassingly low (\~1–3), which is the real story behind the "572 qualified" vanity count.
## Symptom → metric map
Every complaint you raised maps to a concrete, computable diagnostic:
<table header-row="true">
<tr>
<td>Your observation</td>
<td>Quantified by</td>
<td>What "bad" looks like</td>
</tr>
<tr>
<td>"very correlated alphas"</td>
<td>Effective Number of Bets; PC1 variance share; correlation-cluster count</td>
<td>ENB ≪ #alphas; PC1 explains &gt;50%</td>
</tr>
<tr>
<td>"monoculture — every alpha group_neutralize"</td>
<td>Neutralization-type distribution; operator Shannon entropy</td>
<td>One op &gt;90% share; entropy near 0</td>
</tr>
<tr>
<td>"vector_neut never used"</td>
<td>Operator coverage histogram (zero-usage list)</td>
<td>Many operators at 0% usage</td>
</tr>
<tr>
<td>"no variety — same volume strategy"</td>
<td>Archetype/template distribution; field-family HHI; AST structural similarity</td>
<td>One archetype &gt;80%; family HHI near 1</td>
</tr>
<tr>
<td>"the GA didn't beat the seed"</td>
<td>Best/median fitness per generation; lineage concentration</td>
<td>Flat/negative lift; pop descends from 1 seed</td>
</tr>
</table>
---
## Module 1 — Structural / syntactic diversity (the monoculture scan)
No PnL needed; runs on every simulated alpha. Parse each expression to an AST and aggregate.
- **Operator usage histogram + coverage.** Count each operator across all alphas. `coverage = operators_used / operators_available`. Directly surfaces `group_neutralize ≈ 94.5%` and the zero-usage list (`vector_neut`, `group_vector_neut`-absent, etc.).
- **Operator entropy.** Shannon entropy of the usage distribution, normalized: `H = -Σ pᵢ ln pᵢ`, report `H / ln(N_ops)` ∈ \[0,1\]. Near 0 = monoculture.
- **Neutralization-type distribution.** Tabulate `group_neutralize` vs `vector_neut` vs none, and the group key (SECTOR / MARKET / INDUSTRY). This is the headline for your "everything was group_neutralize" claim.
- **Field & field-family concentration (HHI).** Herfindahl index `HHI = Σ sᵢ²` over fields and over families; effective count `= 1/HHI`. The two-field options/vol pool should show HHI near 1 and effective-field-count ≈ 2.
- **Archetype / skeleton distribution.** Collapse each alpha to its top-level template (e.g. `group_neutralize(trade_when(ts_zscore(VOL) > …))`) and count. Quantifies "same volume strategy."
- **Complexity distribution.** Expression depth and node count histograms — an overfit proxy (your qualified pool ran depth 13–18).
- **AST structural similarity.** Average pairwise subtree (n-gram) Jaccard similarity. High = clones.
## Module 2 — Behavioral / semantic diversity (the truth layer)
Needs `alpha_pnl` (now backfilled). Build the daily-return matrix (reuse `decorrelation_selector._daily_returns` for gap-correct differencing), then the correlation matrix `C`.
- **Effective Number of Bets (Meucci).** Eigen-decompose `C = Σ λᵢ`; normalize `pᵢ = λᵢ / Σλ`; `ENB = exp(-Σ pᵢ ln pᵢ)` ∈ \[1, N\]. **The single most important number this system produces.**
- **Dominant-factor share.** `PC1 variance = λ₁ / Σλ`. If one principal component eats &gt;50%, every alpha is essentially that one factor.
- **Correlation-cluster count.** Hierarchical clustering on `1 − |corr|`; count clusters at thresholds (0.5, 0.7). "572 alphas → k behavioral clusters."
- **Mean pairwise \|corr\|** and the full heatmap (sorted by cluster) for the report.
## Module 3 — Overfitting / statistical validity (Bailey & López de Prado)
The antidote to the "572 qualified" mirage.
- **Deflated Sharpe Ratio (DSR)** per alpha, using the **actual trial count (2432)** — *not* the `DEFLATION_MAX_TRIALS=1000` cap — plus the cross-trial Sharpe variance, skew, and kurtosis. Report how many alphas clear DSR significance (expect: very few).
- **Probability of Backtest Overfitting (PBO)** via Combinatorially Symmetric Cross-Validation (CSCV): split the PnL matrix into S slices, and for each combinatorial IS/OOS partition check whether the IS-best ranks below the OOS median; `PBO = P(logit < 0)`. This judges the *selection process*, not individual alphas — exactly our worry.
- **Minimum Track Record Length (MinTRL).** How long a track record each top alpha needs to be statistically real.
- **IS→OOS degradation.** This run's OOS Sharpe column is empty — flag that as a **data gap to fix** (the diagnostic can't validate decay without it), and wire OOS capture into the next run.
## Module 4 — Search / evolution diagnostics (GA health)
Uses the `generation` column to make the GA's failure legible.
- **Diversity over generations.** Operator entropy, field HHI, and ENB computed *per generation* → a collapse curve. This is the textbook **premature-convergence** signature.
- **Per-generation winner base-rate.** Fraction of each generation clearing `MIN_SHARPE`. A clean convergence metric: early generations explore (more losers, low base-rate) and late generations converge (almost all "winners" of one shape). The earnings4 run's 10% → 71% climb is the textbook signature, and it also explains why the surrogate pre-screener had nothing to screen.
- **Fitness progression.** Best & median (raw and deflated) fitness per gen. We already know GA evolved \< best seed (Δ ≈ −0.0515); this quantifies *when* it stalled.
- **Lineage concentration.** What fraction of the final population descends from a single seed. Monoculture's root cause.
- **Operator/mutation productivity.** Fraction of offspring beating their parent, per mutation type — which moves actually help vs. waste compute.
- **Wasted-compute estimate.** Count near-duplicate sims (AST similarity &gt; dedup threshold) — how much of the 2432 was redundant.
- **Reseed effectiveness.** Did injected reseeds survive selection or get washed out immediately?
## Module 5 — Breadth & capacity (Grinold's Fundamental Law)
- `IR ≈ IC × √breadth`. With ENB ≈ 2, your *effective* breadth is \~2 regardless of 572 nominal alphas — so this frames the hard ceiling on achievable information ratio and explains *why* the monoculture caps performance, not just *that* it does.
---
## Run Health Scorecard
Roll the modules into one comparable scorecard (0–100 sub-scores) with explicit targets so future runs get pass/fail gates:
<table header-row="true">
<tr>
<td>Sub-score</td>
<td>Driver metric</td>
<td>Target (healthy)</td>
<td>Expected this run</td>
</tr>
<tr>
<td>Operator diversity</td>
<td>Normalized operator entropy</td>
<td>&gt; 0.6</td>
<td>Low</td>
</tr>
<tr>
<td>Field diversity</td>
<td>Effective field count (1/HHI)</td>
<td>&gt; 8 fields</td>
<td>≈ 2</td>
</tr>
<tr>
<td>Neutralization diversity</td>
<td>Max single-neut share</td>
<td>&lt; 0.5</td>
<td>≈ 0.95</td>
</tr>
<tr>
<td>Behavioral independence</td>
<td>ENB / #qualified</td>
<td>&gt; 0.3</td>
<td>Very low</td>
</tr>
<tr>
<td>Statistical validity</td>
<td>% surviving DSR; PBO</td>
<td>PBO &lt; 0.3</td>
<td>TBD (likely poor)</td>
</tr>
<tr>
<td>Search effectiveness</td>
<td>Evolved vs best-seed fitness lift</td>
<td>&gt; 0</td>
<td>Negative</td>
</tr>
</table>
## Engineering plan — `run_diagnostics.py`
- **Shape:** standalone CLI, read-only on the run DB, mirrors `analyze_run.py`. `python run_diagnostics.py --db <run.db> [--all | --qualified] [--plots]`.
- **Inputs:** `alpha_population` (expr, id, sharpe, turnover, fitness, deflated fitness, generation), `alpha_pnl` (daily series), parsed ASTs.
- **Outputs:**
	- `run_report.md` — human-readable post-mortem (the scorecard + per-module sections).
	- `run_metrics.json` — machine-readable metrics for **cross-run tracking**.
	- Optional plots: correlation heatmap, eigenvalue scree, diversity-over-generation curves, operator histogram.
- **Cross-run memory:** append each run's headline metrics (ENB, entropies, HHIs, DSR-survival, PBO, GA lift) to a `run_diagnostics` table keyed by run id + dataset. **This is the actual "learn from our mistakes" loop** — you watch ENB and operator entropy move run-over-run as you apply fixes.
- **Reuse, don't reinvent:** lean on `decorrelation_selector._daily_returns` / `_pairwise_corr`, `oos_deflation` for the deflation primitives, and `config.field_family()` for family rollups — so the diagnostic agrees with the selector by construction.
### Phased rollout
1. **Phase 1 — Structural (cheap, no PnL):** Module 1 + the scorecard skeleton. Immediately quantifies monoculture/operator-coverage. Ship first.
2. **Phase 2 — Behavioral:** Module 2 (ENB, clusters, heatmap) now that PnL is backfilled.
3. **Phase 3 — Statistical:** Module 3 (DSR with true trial count, PBO/CSCV).
4. **Phase 4 — Evolution:** Module 4 per-generation diagnostics + lineage.
5. **Phase 5 — Cross-run tracking + Grinold framing + plots.**
---
## Implementation notes (v2 — what shipped in `run_diagnostics.py`)
The build implements all five modules + scorecard + cross-run tracking in one standalone, read-only CLI. Where it deliberately *improves on or corrects* this v1 design:
- **Hard read-only at the driver level.** The run DB is opened with sqlite `mode=ro`, and cross-run history is written to a **separate** `diagnostics_history.db` — the run DB is now physically un-writable by the tool, stronger than the v1 "it only reads" promise.
- **Denoised ENB (Marchenko–Pastur), not just raw.** Raw sample-correlation eigenvalues are noise-inflated, which *overstates* independence — raw ENB flatters the monoculture. The tool reports raw **and** RMT-denoised ENB (constant-residual; eigenvalues below λ⁺ = (1+√(N/T))² collapsed to their mean). Denoised ENB is the honest headline.
- **Real CSCV/PBO** on the return matrix (combinatorial balanced IS/OOS block splits, logit of the IS-best's OOS rank), replacing the simplified `oos_deflation.estimate_pbo` proxy.
- **DSR under true N vs capped N side by side.** Shows exactly how much `DEFLATION_MAX_TRIALS=1000` flatters survival vs the true 2432, without mutating the production config.
- **Cluster *representatives*.** Each behavioral cluster is named by its highest-fitness member + archetype — "k clusters" becomes "here are your k actual strategies."
- **Cheap extra signal:** turnover/decay distributions, neutralization group-key split, operator parent→child bigrams, and a **vanity ratio** (qualified count ÷ denoised ENB) in the scorecard.
- **Cross-run deltas**, not just appends: each run's headline metrics are diffed against the prior run so regressions/improvements are flagged — the actual learning loop.
### Lineage instrumentation — NOW IMPLEMENTED (populates on the next run)
These Module 4 metrics were flagged NOT COMPUTABLE in v1 because `alpha_population` had no parent link. That gap is now closed in code, as **passive instrumentation** (not a GA diversity hack — it changes nothing about selection, mutation, or gating; it only records what already happens):
- `db_manager.py` adds three columns — `parent_id`, `mutation_type`, `origin` — via the existing idempotent migration, and writes them **write-once** (`COALESCE`) so a later raw/enrichment re-save can never erase a tag.
- `orchestrator.py` tags every candidate at creation: `seed` / `reseed` / `ga` (with the parent's `alpha_id` + `crossover` vs `crossover+mutation`) / `refine` / `negation` / `universe_sweep`.
- `run_diagnostics.py` reads them when present: **lineage concentration** (offspring-per-parent HHI / effective parent count), **mutation productivity** (fraction of children beating their parent's fitness, per `mutation_type`), and **origin/reseed survival** (qualified rate by `origin`).
Honest limits (stated, not faked): (1) **future runs only** — the existing 2432 rows stay NULL and still report NOT COMPUTABLE; there is no back-fill. (2) **First-discovery lineage** — the `(expression, universe, decay)` UNIQUE upsert collapses a re-discovered alpha onto its first row, so `parent_id` is the *first* parent, not a full genealogy. (3) **Coarse ****`mutation_type`** — `mutate()` picks its operator at random and doesn't report which, so GA mutations are tagged `crossover` / `crossover+mutation`, not per-operator.
This keeps the describe-only discipline: lineage is now *recorded*, so the next run's scorecard can show whether a diversity fix actually moved ENB — but nothing is bolted onto the GA yet.
## Senior-dev caveats (read before trusting the numbers)
- **Behavioral metrics are only as good as PnL coverage.** ENB/PBO computed on a thin PnL subset will lie. Gate them behind the same coverage check the selector uses, and report coverage alongside every behavioral number.
- **ENB depends on the alpha set you feed it.** Qualified-only vs all-2432 give different stories — compute both and label them; don't quietly pick one.
- **PBO/CSCV is data-hungry** and assumes comparable PnL windows; with one dataset and short series it's indicative, not gospel.
- **No single metric is a verdict.** The scorecard is a dashboard; a low ENB plus high archetype concentration plus negative GA lift *together* is the diagnosis. Don't optimize any one number in isolation — that just moves the monoculture somewhere else.
- **Diagnostics describe; they don't fix.** The temptation after seeing ENB ≈ 2 will be to bolt diversity hacks onto the GA. Resist until the scorecard exists and a baseline is recorded, or you can't prove the fix worked.
## References (methodology)
- Bailey & López de Prado, *The Deflated Sharpe Ratio* (2014) — [https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting* (CSCV) — [https://ideas.repec.org/a/rsk/journ0/2471206.html](https://ideas.repec.org/a/rsk/journ0/2471206.html)
- Meucci, *Managing Diversification* (Effective Number of Bets) — [https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1358533](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1358533)
- Burlacu et al., *Population diversity and inheritance in GP for symbolic regression* (2023) — [https://link.springer.com/article/10.1007/s11047-022-09934-x](https://link.springer.com/article/10.1007/s11047-022-09934-x)
- *AlphaAgent: regularized exploration to counteract alpha decay* — [https://arxiv.org/html/2502.16789v2](https://arxiv.org/html/2502.16789v2)