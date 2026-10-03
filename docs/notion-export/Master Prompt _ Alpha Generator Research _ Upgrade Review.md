<callout icon="📋" color="blue_bg">
	Copy the block below into a capable AI (e.g. Claude Opus, ideally one that can see your `BrainForge` code). It's your original request, rewritten in detail and pre-loaded with the research and codebase findings already gathered — so the AI starts grounded instead of from zero, but is still told to verify everything against your actual code.
</callout>
```plain text
ROLE & MINDSET
You are a senior quantitative developer and researcher. Think carefully and for a long
time before answering. Be rigorous and SKEPTICAL — do not flatter me or agree by default.
If an idea is weak, say so plainly and explain why. Your job is to make my automated
alpha-generation system measurably better WITHOUT overcomplicating it or causing overfitting.

GUIDING PRINCIPLE
Code complexity is acceptable IF it buys a real, robust edge. If we can make the system even
~1% better and the gain holds out-of-sample, we implement it — but smartly. The enemies are
(a) overfitting and (b) an over-complicated generator that emits fragile, crowded signals.
Key lesson from our own results: WorldQuant BRAIN rewards SIMPLE, low-turnover, uncrowded
alphas; adding operators/nesting usually RAISES turnover and correlation and LOWERS fitness.
So put the "intelligence" in the SEARCH PROCESS (why a field/operator/structure is chosen),
NOT in deeper per-alpha expressions.

TARGET PLATFORM
We mine cross-sectional equity alphas on WorldQuant BRAIN. Formulas are written in BRAIN's
FASTEXPR language and simulated via REST API. Delay-1 submission bars: Sharpe >= 1.25,
Fitness >= 1.0, turnover within bounds, where Fitness = sqrt(abs(returns)/max(turnover,0.125)) * Sharpe.
BRAIN scores UNCORRELATED baskets highly. Our binding operational constraint is throttled
simulation throughput (only a few concurrent simulations + frequent HTTP 429s), so every
wasted simulation is the scarcest resource we have.

MY SYSTEM ("BrainForge" — VERIFY every claim below against the actual code I give you;
do NOT recommend building something that already exists)
It is an NSGA-II evolutionary alpha factory with: a hybrid seeder (deterministic grammar/
template engine as an always-on floor + an OPTIONAL, off-by-default LLM idea-injector that
contributes only a bounded fraction); AST-based mutation/crossover; dimension-targeted
refinement of promoted winners; a SQLite store (brain_memory.db / alpha_population table)
holding thousands of labeled (expression -> sharpe/turnover/fitness/qualified) rows; and a
regularization stack that ALREADY INCLUDES: Frequent Subtree Avoidance, AST-motif similarity
dedup, originality scoring vs a "crowded alpha zoo" (101 Formulaic Alphas used as an
anti-target), Deflated Sharpe Ratio (Bailey & Lopez de Prado, with corrected excess kurtosis
+ trial capping), an IS-OOS overfitting penalty + a PBO estimate, a MIN_FITNESS gate, slow/
alternative-data seed weighting, operator-field affinity priors, and an ExperienceMemory that
learns from FAILURES (down-weights fields common in losers + pastes a failure digest into the
seed prompt). NOTABLE GAP: we learn from failures but have NO success-side memory — nothing
captures WHY a winner worked and feeds it forward.

YOUR TASKS
1. RESEARCH established, successful alpha-generation platforms and read a few real research
   papers from the internet. Extract what they implemented SUCCESSFULLY, and translate each
   lesson specifically to WorldQuant BRAIN + FASTEXPR (not generic quant advice).
2. CROSS-CHECK every idea against my actual codebase. For each candidate upgrade tell me:
   - Does it already exist in BrainForge? (If yes, say so and move on — don't pad the list.)
   - Concrete VALUE PROPOSITION: what metric it moves (fitness / Sharpe / turnover / diversity
     / OOS robustness / simulation throughput) and roughly how much.
   - Overfitting risk and implementation effort.
   - A clear verdict: BUILD NOW / BUILD LATER / SKIP, with reasoning.
   Rank everything by ROI, explicitly weighting our throughput bottleneck and simple-alpha thesis.
3. HONESTLY EVALUATE my half-baked strategy idea (below). Do not just agree — stress-test it.
4. DELIVER a prioritized, value-proposition-backed upgrade roadmap + your honest verdict on my idea.

RESEARCH STARTING POINTS (learn from these, verify them, and go beyond them):
- AlphaAgent (KDD 2025): Idea->Factor->Eval agent loop + "regularized exploration" (AST
  originality, complexity control, hypothesis alignment) to resist alpha decay.
- "Navigating the Alpha Jungle" (LLM + MCTS): Frequent Subtree Avoidance (top-k) + refinement
  toward the weakest scoring dimension.
- Alpha-GPT: natural-language economic hypothesis -> expression; interpretability.
- FAMA: Cross-Sample Selection (seed the prompt with DECORRELATED example winners) + Chain-of-
  Experience to fight LLM factor homogeneity.
- AlphaForge: generative-predictive mining + DYNAMIC factor combination into a weighted basket.
- AlphaGen (RL, KDD 2023): mine a synergistic SET of alphas, not lone signals.
- Warm-Start Genetic Programming: lock a good structure, search the finite neighborhood.
- Bailey & Lopez de Prado: Deflated Sharpe Ratio + Probability of Backtest Overfitting (CSCV).
- WorldQuant BRAIN docs / community writeups: fitness formula, delay thresholds, turnover floor,
  submission concentration caps, fundamental/news data producing higher-fitness lower-turnover signals.
For each, state plainly whether it is already covered in BrainForge or is a genuine gap.

MY HALF-BAKED STRATEGY IDEA (critique honestly, as a skeptical senior dev):
At the END of each generation, take that generation's submittable winners (there are only a
handful — e.g. ~12 — so token cost stays low) and run them through a highly capable LLM
(e.g. Claude Opus). The LLM would: (a) read the FASTEXPR and explain the logic/economic
meaning of the alpha, (b) flag problems with it, (c) propose an improved expression, and
(d) label the economic value / "what it does", so the system can LEARN from that in the next
generation and use the market insight to spin up new strategies on that alpha. Because we only
analyze the few winners per generation, credit usage stays bounded.
Evaluate this rigorously. At minimum address:
- Is analyzing only winners the right (cheap, high-signal) insertion point? Why or why not?
- Should "explain/label" and "rewrite the expression" be treated as the SAME step or split?
  (Consider that an LLM tends to ADD complexity, which hurts BRAIN fitness.)
- Narrative/look-ahead overfitting: an LLM can invent a plausible economic story for a pure
  multiple-testing fluke. How do we stop that story from steering the next generation badly?
- Could feeding "what made winners win" back into seeding collapse diversity into a monoculture,
  and how would we keep it diversity-aware?
- The LLM only sees the expression text, not realized returns/exposures — how much should we
  trust its "economic value" label, and what real stats should we feed it to ground it?
- How does this idea rank against other upgrades (e.g. learning a surrogate model from our own
  brain_memory.db to pre-screen candidates and beat the simulation-throughput bottleneck)?
Tell me honestly: is it worth building, what exactly would you change, and where does it rank?

HARD CONSTRAINTS FOR ANY RECOMMENDATION YOU MAKE
- The deterministic grammar seeder stays the always-on floor; any LLM contribution is a bounded
  fraction. A weak/missing model must never bottleneck or gate seeding.
- The LLM proposes, BRAIN disposes: every LLM-produced or LLM-edited expression must pass the
  EXISTING gates unchanged (syntax -> live simulation -> fitness/Sharpe/turnover/drawdown ->
  Deflated Sharpe -> self-correlation). No expression is trusted without re-simulation.
- Prefer simpler-or-equal expressions; reject "improvements" that increase AST depth unless they
  also improve realized fitness on the live server.
- Treat any economic label/hypothesis as a HYPOTHESIS, never a hard gate; realized OOS + DSR
  remain the only source of truth.
- New behavior should be feature-flagged and default OFF.

OUTPUT FORMAT
A) Research synthesis: each platform/paper -> the transferable lesson for BRAIN -> already in
   BrainForge or a gap.
B) Ranked upgrade roadmap (table): upgrade | value proposition (metric moved) | overfit risk |
   effort | verdict (build now/later/skip) | does it already exist?
C) Honest verdict on my LLM-in-the-loop idea: what's smart, what's flawed, exactly how you'd
   scope it, and its rank vs the alternatives.
D) A short "do NOT rebuild, it already exists" list so I don't waste effort.
Be concrete, cite the papers you actually used, and keep recommendations tied to moving real
BRAIN metrics.
```