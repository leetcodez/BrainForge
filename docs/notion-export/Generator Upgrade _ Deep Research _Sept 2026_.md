<callout icon="🎯">
	**Diagnosis in one line:** the engine is a well-engineered search algorithm pointed at **0.098% of the search space**, optimising a proxy of the platform's *old* scoring function.
	The GA, the deflation math, the diversity caps, the negation harvest, the checks gate — these are good. Nothing below asks to rewrite them. Every recommendation is about **what the search can reach** and **what it is told to maximise**.
</callout>
## 0. Evidence base
This is not a literature essay — every claim below is measured against our own artefacts.
<table header-row="true">
<tr>
<td>Source</td>
<td>What it gave</td>
</tr>
<tr>
<td>`brain_fields_merged.json` (122,748 fields)</td>
<td>Field-level multiplier, crowding, coverage, type, region, delay, dataset</td>
</tr>
<tr>
<td>`snapshot_narrow` operator detail (84 operators)</td>
<td>The real operator surface by category and scope</td>
</tr>
<tr>
<td>Notion copies of `config.py`, `orchestrator.py`, `llm_seed_generator.py`, `field_harvester.py`</td>
<td>Exact constants and control flow being critiqued</td>
</tr>
<tr>
<td>Bailey & López de Prado (DSR / PBO), Meucci (ENB), AlphaGen / AlphaForge / AlphaAgent / warm-start GP</td>
<td>Method grounding for §3.11–3.13</td>
</tr>
</table>
<callout icon="⚠️">
	**Caveats I will not paper over.** Non-USA/EUR/ASI region counts are lower bounds (old-run 10k truncation). The `themes` array is **empty on every field** in the snapshot — so per-field `pyramidMultiplier` is available but *theme membership* is not; theme targeting needs a separate endpoint we have not scraped. Multi-simulation batching (§3.10) is a hypothesis to probe, not a confirmed capability.
</callout>
---
## 1. The three structural gaps
### Gap A — Reach
`HARVEST_VOCAB_MAX_FIELDS = 120`, `HARVEST_VOCAB_PER_CATEGORY = 20`.
<table header-row="true">
<tr>
<td></td>
<td>Count</td>
</tr>
<tr>
<td>Fields in catalog</td>
<td>122,748</td>
</tr>
<tr>
<td>Fields the engine can ever reference</td>
<td>≤ 120</td>
</tr>
<tr>
<td>**Share of catalog reachable**</td>
<td>**0.098%**</td>
</tr>
<tr>
<td>USA "frontier" fields (mult ≥1.5, ≤50 alphas, cov ≥0.5)</td>
<td>22,289</td>
</tr>
<tr>
<td>**Share of USA frontier reachable**</td>
<td>**0.538%**</td>
</tr>
</table>
### Gap B — Axes
<table header-row="true">
<tr>
<td>Axis</td>
<td>Engine uses</td>
<td>Platform offers</td>
<td>Unused</td>
</tr>
<tr>
<td>Region</td>
<td>1 (`USA` hardcoded)</td>
<td>10</td>
<td>EUR alone = 39,039 fields</td>
</tr>
<tr>
<td>Delay</td>
<td>1 (`DEFAULT_DELAY = 1`)</td>
<td>2</td>
<td>20,875 delay-0 fields</td>
</tr>
<tr>
<td>Universe</td>
<td>4</td>
<td>18</td>
<td>MINVOL1M, TOPSP500, TOPDIV3000…</td>
</tr>
<tr>
<td>Decay</td>
<td>5 `[0,5,10,15,20]`</td>
<td>8</td>
<td>**1, 2, 3** — the fast band</td>
</tr>
<tr>
<td>Vector projection</td>
<td>1 (`vec_avg`)</td>
<td>7</td>
<td>stddev, count, range, max, min, sum</td>
</tr>
<tr>
<td>Grouping key</td>
<td>4 hardcoded</td>
<td>4 + **2,939 GROUP fields**</td>
<td>1,891 in USA</td>
</tr>
</table>
### Gap C — Objective
The fitness function optimises `sqrt(|returns|/max(turnover,0.125)) * Sharpe`, deflated and shape-penalised. It contains **no term** for pyramid multiplier, 2-year Sharpe, PnL realization, or portfolio-level effective bet count — i.e. four of the levers that now decide whether an alpha is worth submitting.
---
## 2. What the catalog actually looks like
Worth internalising before reading the recommendations.
<table header-row="true">
<tr>
<td>Property</td>
<td>Distribution</td>
</tr>
<tr>
<td>Type</td>
<td>MATRIX 93,236 · **VECTOR 26,536** · GROUP 2,939 · SYMBOL 21 · UNIVERSE 16</td>
</tr>
<tr>
<td>Crowding</td>
<td>**65,656 fields have zero alphas.** 102,338 have \<10. p99 = 561</td>
</tr>
<tr>
<td>Pyramid multiplier</td>
<td>2.0→3 · 1.9→5,404 · 1.8→15,301 · 1.7→8,513 · 1.6→6,391 · 1.5→14,143</td>
</tr>
<tr>
<td>Coverage</td>
<td>p10 0.50 · p50 0.91 · p75 1.00</td>
</tr>
<tr>
<td>Frontier by region</td>
<td>USA 22,289 · EUR 13,399 (199 distinct datasets)</td>
</tr>
</table>
The headline: **crowding is not the constraint.** More than half the platform has never had a single alpha written on it. The constraint is that our engine cannot see it.
---
## 3. Findings
### 3.1 · The vocabulary cap is the single biggest loss — but the naive fix breaks the GA
`_load_harvested_vocabulary()` admits 120 fields into `DATA_DICTIONARY`, which is *also* the mutation pool for `GeneticEngine._mutate_field`. So the cap is doing two jobs at once: limiting seed breadth (bad) **and** keeping mutation local (good). Raising it to 122,748 would turn every field mutation into a random teleport across unrelated datasets and destroy GP locality.
**The correct fix is to split the two roles:**
```python
# Tier 1: CANDIDATE POOL — the full ranked frontier, tens of thousands.
#         Used for seeding and for bandit allocation. Never used by mutation.
# Tier 2: ACTIVE WORKING SET — 300-800 fields, rotated each epoch.
#         This is what DATA_DICTIONARY becomes. Mutation stays local.
ACTIVE_SET_SIZE      = 600
ACTIVE_SET_ROTATE_EVERY = 10   # generations
ACTIVE_SET_KEEP_TOP  = 0.4     # carry the productive 40% into the next epoch
```
Each epoch, retire fields that produced nothing and draw replacements from the candidate pool via the bandit in §3.10. This is the warm-start GP result — *GP performs better when focusing on promising regions rather than searching randomly* — applied at the vocabulary level rather than the expression level.
**Expected effect:** the accessible frontier goes from \~120 fields to \~22,000 with a rotating 600-field lens. This is the change that makes every other change matter.
---
### 3.2 · Pyramid multiplier is absent from the ranker and the fitness function
`priorityScore` weights value / maturity / coverage / history / simplicity, then dampens for crowding. It never reads `pyramidMultiplier` — the platform's own published statement of what a field is worth.
The three maximum-multiplier fields on the platform:
<table header-row="true">
<tr>
<td>Field</td>
<td>Dataset</td>
<td>Mult</td>
<td>Alphas</td>
<td>Coverage</td>
</tr>
<tr>
<td>`herfindahl_index_holdings`</td>
<td>fund_holdings_panel</td>
<td>**2.0**</td>
<td>3</td>
<td>1.00</td>
</tr>
<tr>
<td>`holder_account_total`</td>
<td>fund_holdings_panel</td>
<td>**2.0**</td>
<td>4</td>
<td>1.00</td>
</tr>
<tr>
<td>`holding_value_distribution_score`</td>
<td>fund_holdings_panel</td>
<td>**2.0**</td>
<td>7</td>
<td>1.00</td>
</tr>
</table>
Maximum multiplier, full coverage, effectively virgin, present in five regions — and unreachable by the current engine.
**Two changes, not one:**
```python
# (a) ranking
score *= (pyramid_multiplier ** FIELD_PYRAMID_GAMMA)   # gamma ~1.5

# (b) selection — expected submitted value, not raw fitness
expected_value = wq_fitness * pyramid_multiplier_of(expression)
```
Use (b) as a **third NSGA-II objective**, not as a replacement for fitness — a 1.9× multiplier on a mediocre alpha is still a mediocre alpha, and collapsing them into one scalar hides that.
---
### 3.3 · The `Model` exclusion is now backwards
`field_harvester` applies `CATEGORY_MULTIPLIER["Model"] = 0.6` and `SEED_EXCLUDE_CATEGORIES = {"Model"}` — model fields are pre-computed, so a simple transform adds little and correlates. Sound reasoning, written for a small catalog. The data now contradicts it:
<table header-row="true">
<tr>
<td>Dataset</td>
<td>Frontier fields</td>
<td>Max mult</td>
<td>Avg alphas</td>
<td>Avg coverage</td>
</tr>
<tr>
<td>`chart_cnn_alpha`</td>
<td>764</td>
<td>1.8</td>
<td>**0.1**</td>
<td>0.95</td>
</tr>
<tr>
<td>`ai_equity_alpha`</td>
<td>475</td>
<td>**1.9**</td>
<td>1.1</td>
<td>1.00</td>
</tr>
<tr>
<td>`mmp_nlp_sentiment`</td>
<td>446</td>
<td>**1.9**</td>
<td>1.5</td>
<td>0.96</td>
</tr>
<tr>
<td>`ml_factor_proj`</td>
<td>331</td>
<td>**1.9**</td>
<td>4.3</td>
<td>1.00</td>
</tr>
</table>
The platform is attaching its *highest* multipliers to these, and almost nobody is using them. `model` is the 4th-largest frontier category (6,511 fields).
**Don't flip the exclusion to blind inclusion** — the correlation concern is real. Replace the category ban with a **within-family correlation budget**: admit model fields, cap them at \~15% of the active set, and let the PnL-correlation penalty (§3.12) police redundancy empirically rather than by assumption.
---
### 3.4 · Region is hardcoded — and the catalog lets us validate before spending a simulation
`DEFAULT_REGION = "USA"` in `build_settings()`. EUR's 13,399 frontier fields have never been searched, and the same expression in another region is a **distinct submittable alpha** with its own pyramid theme.
The non-obvious win: every field record carries `regions`, `delays` and `universes`. Today an invalid combination costs a full simulation round-trip to discover. With the catalog loaded we can **pre-flight every candidate offline**:
```python
def settings_valid(expression, region, delay, universe):
    for fid in fields_in(expression):
        meta = CATALOG.get(fid)
        if not meta:                      return False
        if region   not in meta.regions:  return False
        if delay    not in meta.delays:   return False
        if universe not in meta.universes: return False
    return True
```
On a queue limited to 3 concurrent simulations, eliminating guaranteed-invalid submissions is pure throughput.
---
### 3.5 · Delay-0 is the densest pocket of value on the platform
<table header-row="true">
<tr>
<td>Delay</td>
<td>USA fields</td>
<td>Frontier</td>
<td>**Frontier density**</td>
</tr>
<tr>
<td>0</td>
<td>16,583</td>
<td>13,687</td>
<td>**82.5%**</td>
</tr>
<tr>
<td>1</td>
<td>79,973</td>
<td>19,510</td>
<td>24.4%</td>
</tr>
</table>
Delay-0 fields are disproportionately high-multiplier and uncrowded. `SUBMISSION_MIN_DELAY0_FRACTION = 0.05` exists in config but is marked *informational* and never enforced anywhere.
Delay-0 carries a stricter bar (`MIN_FITNESS_DELAY0 = 1.3`) — which the engine already handles correctly. Make delay a swept axis and **enforce** the delay-0 quota in the submission selector.
---
### 3.6 · 26,536 vector fields are viewed through one of seven lenses
`_harvested_field_expr()` collapses every VECTOR field with `vec_avg`. The platform exposes seven vector operators. These are not cosmetic variants — they are **economically distinct signals** from the same raw data:
<table header-row="true">
<tr>
<td>Projection</td>
<td>What it actually measures</td>
</tr>
<tr>
<td>`vec_avg`</td>
<td>Consensus level *(all we use today)*</td>
</tr>
<tr>
<td>`vec_stddev`</td>
<td>**Dispersion — analyst disagreement**</td>
</tr>
<tr>
<td>`vec_count`</td>
<td>Attention / coverage breadth</td>
</tr>
<tr>
<td>`vec_range`</td>
<td>Tail spread of opinion</td>
</tr>
<tr>
<td>`vec_max` − `vec_avg`</td>
<td>Skew of the opinion distribution</td>
</tr>
</table>
`vec_stddev(x) / vec_avg(x)` is the coefficient of variation — the classic **analyst-disagreement anomaly**, one of the better-documented cross-sectional effects. The engine cannot currently express it.
USA vector frontier = **6,935 fields**, concentrated in exactly the right places: `analyst_consensus` (2,080), `news12` (574), `ai_equity_alpha` (475).
Add a `_mutate_vector_projection` operator and emit multiple projections per vector field at seed time. Also worth probing: BRAIN's own guidance recommends `group_vector_neut(alpha, ts_ir(returns,240), subindustry)` for risk neutralisation — config notes this operator is **not yet in our ****`operators.json`**, so `probe_wq.py` should re-run against the live 84-operator set.
---
### 3.7 · 2,939 GROUP fields are being discarded as signals when they are grouping keys
The harvester sets `SIMPLICITY_BY_TYPE["GROUP"] = 0.0` and `SEED_EXCLUDE_TYPES = {"GROUP"}`. Correct — they are useless *as signals*. But they are not signals; they are **neutralisation keys**, and we currently use four hardcoded ones.
USA has 1,891 GROUP fields — `pv30` (1,585), `other455` (1,200) — including `country`, `currency`, `exchange`, and statistical cluster labels like `first_method_cluster10_all` and `global_method1_group50`.
Neutralising within a **statistical cluster** instead of a GICS sector produces a signal with near-identical economics and materially different residuals — one of the cheapest decorrelation levers available, because it reuses an already-validated alpha. Harvest GROUP fields into a separate `GROUP_KEYS` pool feeding `{NEUTRALIZATION}` and `_mutate_neutralization`.
---
### 3.8 · The two cheapest fixes on this page
**Decay grid.** `DECAYS = [0, 5, 10, 15, 20]`; the platform supports `0,1,2,3,5,10,15,20`. The engine jumps 0 → 5, skipping the entire fast band where options, IV and event-driven families live. `config.DECAY_FAST_STEMS` explicitly targets those families and then denies them their natural decay range. One-line change.
**Universe grid.** Four of eighteen. `MINVOL1M`, `ILLIQUID_MINVOL1M`, `TOPDIV3000` and `TOPSP500` are *structurally different cross-sections*, not just size cuts — alphas found there are decorrelated from TOP3000 alphas almost by construction. The universe funnel already exists and works; it just has a short list.
---
### 3.9 · The new scoring gates aren't optimised for
The `is.checks` gate correctly *blocks* alphas BRAIN flags. But 2-year Sharpe (cutoff 1.58), PnL realization (cutoff 20) and pyramid multiplier are never **targeted** — `_dimension_scores()` has exactly three axes: sharpe, turnover, correlation.
Parse the checks payload into structured metrics and add two refinement dimensions with their own neighbour generators:
<table header-row="true">
<tr>
<td>Dimension</td>
<td>Weakness</td>
<td>Neighbour move</td>
</tr>
<tr>
<td>`recency`</td>
<td>2Y Sharpe \< 1.58</td>
<td>Shorten windows; recency-weighted decay; drop stale regime gates</td>
</tr>
<tr>
<td>`realization`</td>
<td>PnL realization \< 20</td>
<td>Raise decay, lengthen windows, add `trade_when` gate</td>
</tr>
</table>
This matters because these are *fixable* failures. An alpha failing only on PnL realization is one decay step from submittable, and today nothing in the engine knows to take that step.
---
### 3.10 · Throughput is not the constraint — sample efficiency is
The expanded space is roughly `22,289 fields × 18 templates × 8 decays × 18 universes × 2 delays ≈ 10⁸` configurations, against `MAX_CONCURRENT_SIMULATIONS = 3` and \~7,000 lifetime simulations. **Brute force is not on the table at any concurrency.**
Three compounding responses, in order of value:
1. **Bandit allocation over ****`(dataset × family × template-class)`**** arms.** Thompson sampling, reward = P(promoted). With 199 frontier datasets this is precisely the right granularity, and it is the mechanism that makes the §3.1 rotation intelligent instead of random. This is the highest-leverage algorithmic change on the page after the vocabulary fix.
2. **Turn the surrogate on as a soft prioritiser.** `SURROGATE_ENABLED = 0` today, shadow-only by design. Use it to *rank* the queue, never to block — run `evaluate_prescreener.py` first and keep the false-negative rate visible.
3. **Probe multi-simulation.** Consultant tier advertises multi-simulation. If `/simulations` accepts a list payload, batching 10 expressions per POST is a step change in throughput. Unverified — probe before designing around it.
---
### 3.11 · Mutation neighbourhoods are semantically wrong at 122k scale
`_mutate_field` swaps within `FIELD_GROUPS[group]` — 8 coarse static buckets. "Swap fundamental → fundamental" across a 122k catalog is a random jump between unrelated datasets. GP only works when mutation is **local in economic space**.
The catalog gives us `dataset` → `category` → `subcategory`. Use a graded neighbourhood: same subcategory (p≈0.6) → same dataset (p≈0.3) → same category (p≈0.1).
**And the structure is far richer than the engine exploits.** In the USA frontier alone:
<table header-row="true">
<tr>
<td>Structure</td>
<td>Count</td>
</tr>
<tr>
<td>Term-structure sibling families</td>
<td>**2,309**</td>
</tr>
<tr>
<td>Fields inside them</td>
<td>8,106</td>
</tr>
<tr>
<td>Adjacent spread pairs available</td>
<td>**5,797**</td>
</tr>
<tr>
<td>Complete semantic pairs (long/short, buy/sell…)</td>
<td>**426**</td>
</tr>
</table>
Largest families: `analyst_embedding_component_#N#` (100), `fnd28_value_#N#a` (56), `mean_global_feature_#N#` (40).
The harvester caps this at `SEED_CURVE_SPREAD_MAX = 40` and `MAX_SPREAD_TEMPLATES = 2` — **40 of 5,797**. Raise the caps and promote `_mutate_term_spread` to a first-class mutation operator using a precomputed sibling index. Curve steepness and skew signals are exactly the "uncrowded relative-value" shapes the prompt in `llm_seed_generator` already asks for and the engine cannot reliably build.
---
### 3.12 · Decorrelation is measured structurally when the platform measures it on returns
`RETURN_DECORR_SELECTION_ENABLED = 0`. Fitness shaping uses AST-motif similarity — a proxy for the thing that actually gets alphas rejected. Two structurally different expressions over the same dataset family routinely produce the same PnL stream; that is exactly the ENB collapse the config comments already describe.
- Enable return-decorrelation selection (accept that headline Sharpe **falls** — judge the run on ENB, not max fitness; the config comment says this and it is right).
- Add **Meucci's effective number of bets** as a logged run-level metric next to the existing PBO diagnostic. PBO tells you if you're overfitting; ENB tells you if your basket is one bet wearing ten hats.
- Treat the correlation budget as a **portfolio constraint**, not a per-alpha threshold. `decorrelation_selector.py` does this at submission; the GA does not do it during search, which is where it would actually change what gets bred.
---
### 3.13 · Statistical honesty has to scale with the vocabulary
`DEFLATION_MAX_TRIALS = 1000` caps the multiple-testing penalty to stop late-run fitness collapse. Pragmatic — but if we expand the vocabulary 100× while capping the trial count, the Deflated Sharpe becomes systematically optimistic exactly when we most need it honest.
The literature's answer is not a bigger cap: *"the key is to record all trials and determine correctly the clusters of effectively independent trials."* Count **effectively independent trials** — cluster completed trials by AST motif × field family and use the cluster count as `num_trials`. That number grows with genuine breadth of search and stays flat when the engine is grinding variants of one idea, which is the correct behaviour in both cases.
Separately: every alpha is currently refined against IS metrics, so `REFINE_MAX_BRANCHES = 24` is 24 shots at the same target. Where the platform reports `os.sharpe`, treat it as the only honest selector, and keep the IS-OOS gap penalty doing its job.
---
## 4. Roadmap
Ordered by value per unit of engineering risk. **P0 is where almost all the upside is.**
<table header-row="true">
<tr>
<td>#</td>
<td>Change</td>
<td>Impact</td>
<td>Effort</td>
<td>Risk</td>
</tr>
<tr>
<td>**P0-1**</td>
<td>Two-tier vocabulary + rotating active set (§3.1)</td>
<td>🔥🔥🔥</td>
<td>M</td>
<td>Low — additive</td>
</tr>
<tr>
<td>**P0-2**</td>
<td>Pyramid multiplier in ranking + 3rd objective (§3.2)</td>
<td>🔥🔥🔥</td>
<td>S</td>
<td>Low</td>
</tr>
<tr>
<td>**P0-3**</td>
<td>Decay `1,2,3`  • full universe list (§3.8)</td>
<td>🔥🔥</td>
<td>XS</td>
<td>None</td>
</tr>
<tr>
<td>**P0-4**</td>
<td>Offline settings pre-flight from catalog (§3.4)</td>
<td>🔥🔥</td>
<td>S</td>
<td>None — pure filter</td>
</tr>
<tr>
<td>**P0-5**</td>
<td>Vector projection family + mutation op (§3.6)</td>
<td>🔥🔥🔥</td>
<td>M</td>
<td>Low</td>
</tr>
<tr>
<td>**P1-1**</td>
<td>Region + delay as swept axes (§3.4, §3.5)</td>
<td>🔥🔥🔥</td>
<td>M</td>
<td>Med — settings plumbing</td>
</tr>
<tr>
<td>**P1-2**</td>
<td>Semantic mutation neighbourhoods + term-spread op (§3.11)</td>
<td>🔥🔥</td>
<td>M</td>
<td>Med — GP behaviour</td>
</tr>
<tr>
<td>**P1-3**</td>
<td>GROUP fields as neutralisation keys (§3.7)</td>
<td>🔥🔥</td>
<td>S</td>
<td>Low</td>
</tr>
<tr>
<td>**P1-4**</td>
<td>Model category: ban → budget (§3.3)</td>
<td>🔥🔥</td>
<td>S</td>
<td>Med — correlation</td>
</tr>
<tr>
<td>**P1-5**</td>
<td>Recency + realization refinement axes (§3.9)</td>
<td>🔥🔥</td>
<td>M</td>
<td>Low</td>
</tr>
<tr>
<td>**P2-1**</td>
<td>Thompson bandit over dataset×family arms (§3.10)</td>
<td>🔥🔥🔥</td>
<td>L</td>
<td>Med</td>
</tr>
<tr>
<td>**P2-2**</td>
<td>Surrogate as soft prioritiser (§3.10)</td>
<td>🔥🔥</td>
<td>M</td>
<td>Med — FN rate</td>
</tr>
<tr>
<td>**P2-3**</td>
<td>Return-decorrelation on + ENB metric (§3.12)</td>
<td>🔥🔥</td>
<td>M</td>
<td>Med — Sharpe falls</td>
</tr>
<tr>
<td>**P2-4**</td>
<td>Effective-independent-trial counting (§3.13)</td>
<td>🔥</td>
<td>M</td>
<td>Low</td>
</tr>
<tr>
<td>**P2-5**</td>
<td>Probe multi-simulation batching (§3.10)</td>
<td>❓</td>
<td>S</td>
<td>Unknown</td>
</tr>
</table>
<callout icon="🧭">
	**If you only do three things:** P0-1 (reach), P0-2 (aim at the right target), P0-5 (unlock 26,536 vector fields). Those three alone take the engine from 120 fields and one lens to \~22,000 fields and seven, aimed at the platform's own value signal.
</callout>
---
## 5. Instrumentation — how we'll know it worked
Expanding the search space *guarantees* more raw simulations. It does not guarantee more submittable alphas, and the existing metrics won't distinguish the two. Log per generation, before changing anything, so we have a baseline:
<table header-row="true">
<tr>
<td>Metric</td>
<td>Why</td>
</tr>
<tr>
<td>Distinct fields / datasets touched</td>
<td>Did reach actually increase, or just volume?</td>
</tr>
<tr>
<td>Promotion rate per 100 sims</td>
<td>The real efficiency number</td>
</tr>
<tr>
<td>Mean pyramid multiplier of promoted alphas</td>
<td>Is the new objective biting?</td>
</tr>
<tr>
<td>**ENB of the elite basket**</td>
<td>Are we breeding one bet or ten?</td>
</tr>
<tr>
<td>PBO</td>
<td>Existing — keep it visible</td>
</tr>
<tr>
<td>Effective independent trials</td>
<td>Honest denominator for DSR</td>
</tr>
<tr>
<td>Failure reasons by category</td>
<td>Which gate is actually binding</td>
</tr>
<tr>
<td>Sims wasted on invalid settings</td>
<td>Should go to \~0 after P0-4</td>
</tr>
</table>
---
## 6. What *not* to do
- **Don't raise ****`HARVEST_VOCAB_MAX_FIELDS`**** to 100,000.** It is the mutation pool. Without the two-tier split it destroys GP locality and the run gets worse, not better.
- **Don't drop the crowding penalty** because 65,656 fields have zero alphas. Zero alphas on a *high-multiplier, high-coverage* field is opportunity; zero alphas on a sparse, low-coverage field is usually a reason.
- **Don't chase raw simulation throughput first.** At 10⁸ configurations, a 3× concurrency gain is noise. Sample efficiency (P2-1, P2-2) is worth orders of magnitude more.
- **Don't judge the return-decorrelation run on Sharpe.** It will fall. That is the intended behaviour and the config already warns about it.
- **Don't trust ****`complete: true`**** from any ledger** — including the ones I write. Assert positive coverage, not absence of failure. That lesson cost us six regions last week.