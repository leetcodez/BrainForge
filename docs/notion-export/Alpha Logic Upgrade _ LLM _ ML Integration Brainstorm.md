<callout icon="🎯" color="blue_bg">
	**The reframe that matters before any code:** your complaint is "the alphas have no logic." The fix is *not* to make each expression deeper or more complex — your own <mention-page url="https://app.notion.com/p/bc4fdf5bb3b8447193a7034ec1e90fae"/> doc already proves complexifying a simple winner *raises* turnover + correlation and *lowers* BRAIN fitness. The logic should live in the **search process** — *why* a field, operator, structure, or pairing is chosen — not in more nesting per alpha. Every idea below adds *reasoning to the decision*, while keeping the emitted alpha simple and submittable.
</callout>
## Where the generator is "logic-free" today
A precise diagnosis of the current pipeline, so each upgrade targets a real gap:
- **Seeding is grammar-random.** `fill_template` substitutes placeholders by weighted *random* choice. The soft operator–field affinity prior (`OPERATOR_AFFINITY`) is the only economic logic, and it's hand-coded stem matching — it has no idea what `best_fit_implied_announcement_effect` *means*.
- **The LLM is a bolt-on, off by default.** `LLMSeedGenerator` calls the model once, parses a JSON array of one-line expressions, materializes a bounded fraction, and never speaks to it again. There is **no hypothesis, no critique, no feedback loop, no memory of which ideas worked.** It's a fancier random seeder, not a reasoner.
- **Evolution is structurally blind.** `GeneticEngine` does AST subtree grafting + constant/field mutation. Crossover doesn't know if a graft is *economically* coherent — it just produces syntactically valid trees.
- **Failure feedback is shallow.** `ExperienceMemory` down-weights fields that appear in losers and pastes a text digest into the prompt. It reasons about *fields*, never about *mechanisms* ("reversal signals are decaying this regime").
- **No learning across runs.** `brain_memory.db` has thousands of (expression → sharpe/turnover/fitness/qualified) rows. Nothing trains on it. Every run re-derives the same lessons by burning live, 429-throttled simulations.
- **Alphas are submitted solo.** No model combines the mined pool into a portfolio signal, even though BRAIN explicitly rewards uncorrelated baskets.
<callout icon="🧭" color="gray_bg">
	Guiding principle for everything below: **simple alpha, smart search.** Add economic reasoning, learned priors, and feedback loops *around* the generator. Keep each emitted expression a shallow, low-turnover, uncrowded signal — that's what scores.
</callout>
## Prioritized bets
<table fit-page-width="true" header-row="true">
<tr>
<td>#</td>
<td>Idea</td>
<td>What "logic" it adds</td>
<td>Type</td>
<td>Impact / Effort</td>
</tr>
<tr>
<td>1</td>
<td>**Surrogate ML pre-screener** (predict Sharpe/qualify before simulating)</td>
<td>Learns from your own DB what *actually* works; stops wasting throttled sims</td>
<td>ML</td>
<td>Very High / Med</td>
</tr>
<tr>
<td>2</td>
<td>**Hypothesis→Factor→Critique LLM loop** (AlphaAgent-style)</td>
<td>Every alpha is born from a stated economic mechanism, then checked for logic drift</td>
<td>LLM</td>
<td>High / Med</td>
</tr>
<tr>
<td>3</td>
<td>**LLM semantic field-pairing** from harvested descriptions</td>
<td>Real meaning behind spreads/skews instead of stem heuristics</td>
<td>LLM</td>
<td>High / Low</td>
</tr>
<tr>
<td>4</td>
<td>**Learned search controller** (bandit over families/operators/regions)</td>
<td>Replaces static `SEED_FIELD_GROUP_WEIGHTS` with weights learned from realized reward</td>
<td>ML</td>
<td>High / Med</td>
</tr>
<tr>
<td>5</td>
<td>**LLM as a semantic mutation operator** inside the GA</td>
<td>Edits target the alpha's real weakness with an economic reason</td>
<td>LLM</td>
<td>Med / Med</td>
</tr>
<tr>
<td>6</td>
<td>**Factor-combination / meta-alpha model** (AlphaForge-style)</td>
<td>Turns the mined pool into a dynamically-weighted basket</td>
<td>ML</td>
<td>High / High</td>
</tr>
<tr>
<td>7</td>
<td>**Diversity-guided in-context examples + multi-agent debate** (FAMA / FactorMAD)</td>
<td>Directly attacks your monoculture problem at the prompt level</td>
<td>LLM</td>
<td>Med / Low</td>
</tr>
<tr>
<td>8</td>
<td>**Embedding-based novelty** (semantic dedup beyond AST Jaccard)</td>
<td>Catches same-idea-different-shape crowding</td>
<td>ML</td>
<td>Med / Low</td>
</tr>
</table>
---
## A. LLM integrations (reasoning & ideation)
### 1. A real hypothesis-driven loop, not a one-shot seeder
This is the single biggest "add logic" win. Replace the fire-and-forget `_call_llm` with the closed loop the SOTA frameworks (AlphaAgent, Alpha-GPT, FactorMiner) converge on — three roles, which you can run as three prompts to the same model:
- **Idea agent** → proposes a *market hypothesis* in plain English grounded in a specific data family you actually have: *"Post-earnings announcement drift is under-priced on names with rising option-implied move but flat analyst revisions."*
- **Factor agent** → translates the hypothesis into a FASTEXPR expression using your real fields + operators (it already gets the dictionary + operator list).
- **Critic agent** → answers one question: *"Does this math actually express that hypothesis?"* Reject on logic drift before a single simulation is spent.
The hypothesis string travels with the alpha all the way into `brain_memory.db` (add a `hypothesis` column). Now your `ExperienceMemory` digest can feed back *mechanisms*, not just fields: "these 5 hypotheses failed → propose structurally different inefficiencies." That is the difference between a search that *reasons* and one that *samples*.
<callout icon="⚙️" color="gray_bg">
	Fits cleanly into `llm_seed_generator.py`: keep the deterministic grammar backbone as the always-on floor (so a weak model can never bottleneck seeding — your current design is right), but make the LLM fraction *hypothesis-conditioned* and route its output through the critic before `_materialize`.
</callout>
### 2. Semantic field-pairing from descriptions you already harvest
`field_harvester.py` already pulls each field's `description`, and `config._load_field_family_map` already reads it — but only for keyword routing. Feed batches of `(id, description)` to an LLM and ask it to nominate **economically meaningful pairs and spreads**: call-vs-put IV → skew, near-vs-far tenor → term structure, estimate-vs-actual → surprise. Today `_attach_curve_spread_seeds` finds these by regex on numeric stems and a hard-coded `_SEMANTIC_PAIRS` list — an LLM that *reads the descriptions* will find pairings your stems miss entirely (this is exactly why earnings4's English field ids broke your stem routing). Output becomes new `seed_pool.json` spread templates — no change to the downstream engine.
### 3. LLM as a semantic mutation / refinement operator
Your `GeneticEngine` mutates by random graft + constant tweak; `_refine` hill-climbs by fixed dimension. Add an optional **LLM mutation**: give it the expression, its failure reason, and the target axis ("turnover 0.9, need \< 0.7") and ask for an economically-motivated edit (slower data, add a `trade_when` regime gate, lengthen decay). This is "guided GP" — the edits carry a *why*. Keep it a bounded fraction of mutations so it never starves the cheap random operators or the sim queue.
### 4. Diversity-guided examples + a 2-agent debate (cheap, high ROI on your monoculture)
Your `SKELETON_MAX_FRACTION` / FSA fight homogeneity *after* generation. FAMA's finding: LLMs collapse to one factor shape unless you **seed the prompt with low-correlation examples** (Cross-Sample Selection). You already track winner motifs — feed the most *decorrelated* recent winners as in-context examples instead of random ones. Optionally add a lightweight **proposer-vs-skeptic debate** (FactorMAD): one model proposes, one argues why it's crowded/over-fit, then a final synthesis. Two extra calls per batch, materially more original ideas.
---
## B. ML integrations (learning from your own data)
### 5. Surrogate model: predict before you simulate ⭐ top pick
You are sitting on the highest-ROI upgrade and it isn't even an alpha idea — it's a **filter**. Every row in `alpha_population` is a labeled training example: features = AST motifs + operators used + field families + decay + neutralization + universe + parsimony depth; labels = realized `sharpe`, `turnover`, `fitness`, `is_qualified`. Train a gradient-boosted model (LightGBM/XGBoost) offline on the DB and use it online to **rank the candidate batch and simulate the top fraction first**. 
Why this matters more than anything else here:
- Your run is bottlenecked by `MAX_CONCURRENT_SIMULATIONS = 3` and sustained 429s. Every wasted simulation is the scarcest resource you have. A surrogate that kills the bottom 60% of obvious losers *triples your effective throughput* without touching the rate limit.
- It's genuine learned logic about "what works on BRAIN for *us*," and it compounds every run as the DB grows. This is surrogate-assisted evolution — standard in expensive-evaluation GP.
- Zero risk to alpha quality: it only reorders the queue; the real simulation + DSR gates are unchanged.
### 6. Learned search controller (contextual bandit / RL-lite)
Today `SEED_FIELD_GROUP_WEIGHTS`, `NEUTRALIZATION_WEIGHTS`, and affinity weights are hand-tuned constants. Make them **learned**: a contextual bandit treats "which field family / operator / neutralization / region to try next" as arms and updates from realized fitness (Thompson sampling over a Beta/Normal posterior per arm). The search *re-allocates itself* toward whatever is actually paying off this run / dataset — the data-first thesis, but adaptive instead of static. Drop-in: it just supplies the weights the seeder already consumes.
### 7. Factor-combination / meta-alpha model (AlphaForge-style)
Right now winners are submitted individually (`MAX_SUBMISSIONS_PER_RUN = 10`). The literature's biggest portfolio gain comes from **dynamically combining** mined factors: learn time-varying weights over your qualified pool (even a rolling ridge/IC-weighted combiner) to produce a meta-signal, and use *marginal contribution to the basket* as the submission selection rule. Your `submit_to_worldquant.py` already gestures at diversification — this makes it a model. Bigger lift, but it's where "a pile of okay alphas" becomes "a portfolio."
### 8. Embedding novelty + regime conditioning (two smaller adds)
- **Embedding novelty:** complement AST-motif Jaccard with embeddings of the *expression + its hypothesis*. Catches "same idea, different shape" crowding that structural motifs miss; a cosine-distance term folds straight into your originality multiplier in `oos_deflation.py`.
- **Learned regime gate:** your `trade_when` gates fire on random z-score thresholds. Train a cheap regime classifier (vol state, dispersion) and let alphas condition on *learned* market state instead of an arbitrary constant — turning a random gate into an economic one.
---
## Suggested phasing
<table fit-page-width="true" header-row="true">
<tr>
<td>Phase</td>
<td>Ship</td>
<td>Why first</td>
</tr>
<tr>
<td>**1 — Learn from what you have**</td>
<td>#5 surrogate pre-screener, #8 embedding novelty</td>
<td>Pure upside, no new alpha risk, immediately relieves the 429 bottleneck</td>
</tr>
<tr>
<td>**2 — Add reasoning to ideation**</td>
<td>#2 hypothesis loop, #3 semantic field-pairing, #7 diversity examples</td>
<td>This is the actual "give the alphas logic" request; backbone stays as the safety floor</td>
</tr>
<tr>
<td>**3 — Make the search adaptive**</td>
<td>#4 bandit controller, #5 LLM semantic mutation</td>
<td>Once you trust the surrogate + hypotheses, let the loop self-allocate</td>
</tr>
<tr>
<td>**4 — Portfolio thinking**</td>
<td>#6 combination model, regime gates</td>
<td>Highest ceiling, biggest build — do it when single-alpha flow is solid</td>
</tr>
</table>
## Honest caveats (senior-dev hat on)
- **Don't let "logic" become "complexity."** The data-first doc is right: BRAIN pays for simple, uncrowded, low-turnover signals. Use the LLM/ML to choose *better simple alphas*, not to nest five operators. Keep `PARSIMONY_COEFFICIENT` and the skeleton cap honest.
- **The LLM must never bottleneck or gate alone.** Your current "grammar backbone is always-on, LLM is a bounded fraction" design is exactly correct — preserve it. Every LLM output still passes the syntax validator, DSR, fitness, and self-correlation gates.
- **Surrogate drift.** Retrain on a rolling window; a model trained on old regimes will mis-rank. Log surrogate-predicted vs realized to monitor it.
- **Hypotheses can be plausible nonsense.** Keep the live simulation + DSR as the only source of truth; the LLM proposes, BRAIN disposes. The win is a higher *base hit rate* and real interpretability, not a guarantee.
- **Cost.** A hypothesis/critique/debate loop is many more tokens. Gemini Flash / a local Ollama model is fine for this — you already support both.
## Sources
- [AlphaAgent — hypothesis/factor/eval agents, regularized exploration vs alpha decay](https://arxiv.org/html/2502.16789v2)
- [Alpha-GPT — human-AI interactive alpha mining](https://arxiv.org/abs/2308.00016)
- [FAMA — Cross-Sample Selection + Chain-of-Experience to fight LLM factor homogeneity](https://aclanthology.org/2024.findings-acl.233.pdf)
- [FactorMAD — multi-agent debate for interpretable factor mining](https://dl.acm.org/doi/10.1145/3768292.3770377)
- [AlphaForge — generative-predictive mining + dynamic factor combination](https://arxiv.org/html/2406.18394v5)
- [Warm-Start Genetic Programming for alpha mining](https://arxiv.org/html/2412.00896v1)
- [FactorMiner — LLM + experience memory, self-evolving discovery](https://medium.com/jin-system-architect/factorminer-llm-experience-memory-a-self-evolving-alpha-discovery-agent-40b65a4f97e2)