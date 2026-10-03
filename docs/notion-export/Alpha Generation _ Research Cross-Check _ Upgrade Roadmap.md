<callout icon="🎯" color="blue_bg">
	**Thesis that governs every verdict below.** BRAIN rewards *simple, low-turnover, uncrowded* alphas. The Fitness formula `sqrt(abs(returns) / max(turnover, 0.125)) * Sharpe` structurally punishes turnover and rewards return-per-unit-churn, so deeper expressions usually *lose*. Therefore the intelligence belongs in the **search process** (what to try next, what to skip), not in the per-alpha expression. The binding constraint is **simulation throughput** (few concurrent sims + 429s), so the single most valuable thing any upgrade can do is **waste fewer simulations**.
</callout>
<empty-block/>
This doc verifies each researched idea against the actual BrainForge code, gives a concrete value proposition, and ends with a ranked roadmap and an honest verdict on the LLM-in-the-loop idea. Skeptical by design — ideas that are already covered or don't fit BRAIN are called out, not padded.
## A) Research synthesis — lesson → BRAIN translation → already in BrainForge?
### AlphaAgent (KDD 2025) — Idea→Factor→Eval + regularized exploration
The real contribution isn't the three agents; it's that decay-resistance comes from *regularizers* bolted onto generation: AST originality, complexity control, and hypothesis alignment.
- **BRAIN translation:** generate from an economic hypothesis, penalize complexity, score originality against crowded factors.
- **Status:** The regularization stack is **already in BrainForge** (originality vs the 101-alpha crowded zoo, FSA, parsimony in `_composite_fitness`, DSR). The genuine **gap** is the *hypothesis-first* half — nothing in BrainForge states an economic mechanism before seeding.
### Navigating the Alpha Jungle (AAAI 2026, arXiv 2505.11122) — LLM + MCTS, FSA, weakest-dimension refinement
- **BRAIN translation:** top-k Frequent Subtree Avoidance for diversity; refine an alpha by attacking its worst-scoring dimension.
- **Status:** **Already implemented — both of them.** `_refresh_avoid_motifs` is top-k FSA; `_pick_target_dimension` is a softmax over per-axis health (Sharpe / turnover-band / correlation) that attacks the weakest axis. The only unimplemented piece is MCTS itself, and it is **not worth adding** over your NSGA-II + refinement (see roadmap).
### Alpha-GPT — natural-language hypothesis → expression, interpretability
- **BRAIN translation:** attach a human-readable economic rationale to each alpha so the search is steerable and auditable.
- **Status:** **Gap** (no economic labels), but low standalone value. Folds into the hypothesis-first and success-memory items rather than being its own build.
### FAMA (ACL 2024 Findings) — Cross-Sample Selection + Chain-of-Experience
FAMA's measured finding: naive in-context LLM factor mining collapses into **homogeneous** factors. The fix that worked: seed the prompt with **decorrelated** example factors (CSS) and carry a chain of past experience.
- **BRAIN translation:** if you ever feed winners back into seeding, feed *decorrelated* winners only, clustered by correlation — never the raw top-K.
- **Status:** You have **failure-side** memory; **success-side, diversity-aware memory is the named gap.** This is the cheap, high-value build, and it is also the guardrail that makes the LLM idea safe.
### AlphaForge (AAAI 2025) — generative-predictive mining + *dynamic* combination weights
- **BRAIN translation:** combine factors into a basket with time-varying weights.
- **Status:** **Largely inapplicable, SKIP.** AlphaForge's edge is a dynamic combination model that re-weights factors daily inside a portfolio *you control*. On BRAIN you submit **individual** alphas; you don't manage a live combined book whose weights you re-optimize. The transferable sliver — assemble a *decorrelated basket* at submission — you already approximate in `_diversified_order` (category cap + AST-similarity dedup).
### AlphaGen (KDD 2023) — RL for a *synergistic set*, not lone signals
The one true idea: optimize each alpha for its **marginal contribution to a set**, not its standalone score. But the follow-up (AlphaQCM) documents AlphaGen's non-stationarity and reward-sparsity problems — it's fragile and heavy.
- **Status:** The *intent* is **already approximated** — NSGA-II rewards diversity, plus a self-correlation gate and diversity-aware submission ordering. Full RL is **SKIP**: high effort, fragile, and your throughput budget can't feed an RL learner enough live sims.
### Warm-Start Genetic Programming — lock structure, search the finite neighborhood
- **Status:** **Already implemented.** This is exactly the dimension-targeted refinement (settings → windows → wraps tiers) on promoted/near-winners.
### Bailey & López de Prado — Deflated Sharpe + PBO/CSCV
- **Status:** **Already implemented** (DSR with excess-kurtosis correction + trial capping, plus a PBO estimate). Only possible refinement: confirm the PBO estimator is CSCV-style combinatorial; if it's a cheaper proxy, upgrading it is a *small* later task, not a priority.
### Surrogate-assisted evolutionary algorithms (SAEA / GP-surrogate literature)
Not in your starting list, but it's the most important one for your constraint. The established result: train a cheap ML model to **predict fitness from the genotype** and pre-filter individuals, sending only the promising ones to the expensive evaluator (Pilát's GP-surrogate; the SAEA survey literature).
- **BRAIN translation:** train a model on `alpha_population` (AST motifs, operators, field family, decay, neutralization, universe → Sharpe / fitness / qualified) and rank candidates *before* spending a throttled live simulation on them.
- **Status:** **Pure gap, and it attacks the binding constraint directly.** This is the #1 build.
### WorldQuant BRAIN specifics (verified)
- Fitness `= sqrt(abs(returns)/max(turnover,0.125)) * Sharpe` — **verified** (Glazar). Implemented as `worldquant_fitness`.
- Concentration guidance: avoid \>30% of alphas in any single Region×Delay×Data-Category intersection; submit ≥5% at Delay-0 — **verified** (BRAIN starter docs). Category cap is implemented (`SUBMISSION_MAX_CATEGORY_FRACTION`); the **Delay-0 ≥5% guidance is not addressed** (minor).
- Lower turnover + fundamental/news/alt data → higher-fitness, lower-turnover signals — **verified** (Glazar seminar). Already reflected in slow/alt-data seed weighting.
## B) Ranked upgrade roadmap
<table fit-page-width="true" header-row="true">
<tr>
<td>#</td>
<td>Upgrade</td>
<td>Value proposition (metric moved)</td>
<td>Overfit risk</td>
<td>Effort</td>
<td>Verdict</td>
<td>Exists?</td>
</tr>
<tr>
<td>1</td>
<td>**Surrogate pre-screener** (LightGBM on `alpha_population`) ranks candidates; simulate only top fraction</td>
<td>**Throughput** — the binding constraint. \~2–3× effective sims/hour by not wasting the queue on predicted losers</td>
<td>Low — it only *gates*; BRAIN still disposes via live sim</td>
<td>Med</td>
<td>**BUILD NOW**</td>
<td>No</td>
</tr>
<tr>
<td>2</td>
<td>**Success-side, decorrelated memory** (FAMA CSS): cluster OOS-surviving winners by correlation, feed back only cluster reps</td>
<td>**Diversity + seed quality**; closes your named gap without monoculture</td>
<td>Low–Med if exemplars are decorrelated + capped</td>
<td>Low</td>
<td>**BUILD NOW**</td>
<td>No (failure-side only)</td>
</tr>
<tr>
<td>3</td>
<td>**Hypothesis-first economic seeding** (AlphaAgent/Alpha-GPT), non-gating label stored per alpha</td>
<td>**Originality / decay-resistance**; steerable search</td>
<td>Med — narrative overfitting; mitigate by never gating on it</td>
<td>Med</td>
<td>**BUILD LATER**</td>
<td>Partial (regularizers yes, hypothesis no)</td>
</tr>
<tr>
<td>4</td>
<td>**Surrogate-guided seed allocation** (bandit replaces static `SEED_FIELD_GROUP_WEIGHTS`/affinity)</td>
<td>**Search efficiency** — spend seeds where reward is learned, not hand-set</td>
<td>Low–Med</td>
<td>Med</td>
<td>**BUILD LATER** (after #1)</td>
<td>No (static weights today)</td>
</tr>
<tr>
<td>5</td>
<td>**LLM semantic crossover/critic** as a bounded, default-off mutation op on the (genuinely blind) crossover</td>
<td>**Diversity / originality** on recombination</td>
<td>Med — must hard-gate AST depth ≤ parents</td>
<td>Med</td>
<td>**BUILD LATER**</td>
<td>No</td>
</tr>
<tr>
<td>6</td>
<td>MCTS expression search (Alpha Jungle)</td>
<td>Marginal — redundant with GA + weakest-dim refinement</td>
<td>Med</td>
<td>High</td>
<td>**SKIP**</td>
<td>Effectively (FSA + refinement)</td>
</tr>
<tr>
<td>7</td>
<td>Full RL synergistic-set generator (AlphaGen)</td>
<td>Low net — fragile, non-stationary, sim-hungry</td>
<td>High</td>
<td>High</td>
<td>**SKIP**</td>
<td>Approximated by NSGA-II diversity</td>
</tr>
<tr>
<td>8</td>
<td>AlphaForge dynamic combination model</td>
<td>\~0 on BRAIN — you submit single alphas, not a re-weighted book</td>
<td>—</td>
<td>High</td>
<td>**SKIP**</td>
<td>Diversity-aware submit already approximates the usable sliver</td>
</tr>
</table>
<empty-block/>
Reason for the ordering: #1 and #2 both spend **zero API credits**, train on **data you already have**, and respectively attack the **throughput bottleneck** and the **named success-memory gap** — the two highest-leverage, lowest-overfit moves. Everything LLM-driven sits below them because it costs credits, risks narrative overfitting, and must stay a bounded fraction.
## C) Honest verdict on the LLM-in-the-loop idea
**Short version: the instinct is half-right. Keep the cheap labeling slice, drop the rewrite slice, and fix the insertion point.**
- **"Analyze only winners" — wrong framing for the main value.** Winners are few *and* survivorship-biased; an LLM staring at 12 survivors learns the monoculture, not the edge. Your richest, cheapest signal lives in the **thousands of labeled rows you already have** — which is exactly what the surrogate (#1) exploits and the LLM cannot match on cost. Winners are the right input for *labeling/memory*, not for finding what to try next.
- **Split "explain/label" from "rewrite" — yes, hard split.** Explain/label is cheap, safe, and feeds success-memory. **Rewrite is the dangerous part:** LLMs add operators and nesting, which on BRAIN *raises* turnover and correlation and *lowers* fitness — your own documented failure mode. If you ever enable rewrite, gate it brutally: reject any child with AST depth \> parent, and keep it only if **realized** fitness improves on re-simulation. Default off.
- **Narrative / look-ahead overfitting is real and unavoidable** — an LLM will manufacture a clean story for a pure multiple-testing fluke. Three defenses: (a) the label is **never a gate and never directly seeds** — it only becomes a decorrelated exemplar; (b) **state the hypothesis before knowing which alpha won** (hypothesis-first), so a story can't be reverse-engineered onto a fluke; (c) only let a winner's "lesson" propagate **after it survives OOS/DSR**, not after a single lucky generation.
- **Monoculture risk is real** — feeding "what made winners win" into seeding directly fights your FSA and skeleton-diversity machinery. The only safe version is FAMA-style: cluster winners by correlation, feed forward **cluster representatives only**, cap their share of the seed budget, and keep the grammar floor always-on.
- **Don't trust a text-only economic label.** The LLM sees a string, not realized behavior. Ground it with stats you already store: Sharpe, turnover, returns, OOS Sharpe, max self-correlation, dominant data category, and `failed_checks`. A label contradicted by the stats is discarded.
- **Rank vs the surrogate: the surrogate wins decisively.** It attacks the binding constraint on *every* candidate, costs no credits, and uses existing data. The LLM loop is a secondary, narrative-quality enhancement.
**What I'd actually build:** the **explain/label → decorrelated success-memory** slice only (idea item #2, with LLM labeling optional and default-off), and **not** the rewrite. Ranked **#2 overall**, strictly behind the surrogate.
## D) Do NOT rebuild — already in BrainForge
- Frequent Subtree Avoidance (top-k over winner motifs)
- Weakest-dimension / warm-start refinement (covers Alpha Jungle refinement *and* Warm-Start GP)
- AST-motif similarity dedup + originality vs the crowded 101-alpha zoo
- Deflated Sharpe (excess-kurtosis correction + trial capping) + PBO estimate
- `MIN_FITNESS` / `worldquant_fitness` gate + turnover-band handling
- Submission category-concentration cap + diversity-aware ordering
- Failure-side ExperienceMemory (loser field down-weighting + failure digest)
- Operator–field affinity priors and per-family decay priors
- NSGA-II diversity with turnover treated as a target band, not "lower is always better"
## Sources
- AlphaAgent (KDD 2025): [https://arxiv.org/abs/2502.16789](https://arxiv.org/abs/2502.16789)
- Navigating the Alpha Jungle (AAAI 2026): [https://arxiv.org/abs/2505.11122](https://arxiv.org/abs/2505.11122)
- FAMA (ACL 2024 Findings): [https://aclanthology.org/2024.findings-acl.233.pdf](https://aclanthology.org/2024.findings-acl.233.pdf)
- AlphaForge (AAAI 2025): [https://arxiv.org/abs/2406.18394](https://arxiv.org/abs/2406.18394)
- AlphaGen (KDD 2023): [https://arxiv.org/abs/2306.12964](https://arxiv.org/abs/2306.12964)
- AlphaQCM (AlphaGen critique): [https://openreview.net/forum?id=IS7kW28VVt](https://openreview.net/forum?id=IS7kW28VVt)
- GP surrogate pre-filtering: [https://github.com/martinpilat/gp-surrogate](https://github.com/martinpilat/gp-surrogate)
- SAEA model-management survey: [https://arxiv.org/html/2503.00844v1](https://arxiv.org/html/2503.00844v1)
- BRAIN fitness formula + turnover/decay lessons (Glazar): [https://jglazar.github.io/projects/wq_project/](https://jglazar.github.io/projects/wq_project/)
- BRAIN concentration / delay-0 guidance: [https://www.scribd.com/document/728780335/World-Quant-Brain-Alpha-Documentation](https://www.scribd.com/document/728780335/World-Quant-Brain-Alpha-Documentation)