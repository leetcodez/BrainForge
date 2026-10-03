<callout icon="🎯" color="blue_bg">
	Thesis from the research: **the edge is not in the seed formulas — it's in (1) the data you feed them, (2) how aggressively you enforce diversity/originality, and (3) how honestly you punish overfitting.** Your pipeline already has the right skeleton (hybrid seeding → validate → simulate → DSR/NSGA-II → refine → breed). The upgrades below sharpen the three levers that actually move money on BRAIN.
</callout>
## Where the edge actually comes from
Every modern system converges on the same division of labor: a **generator proposes structurally-sound ideas**, and an **algorithmic search evolves them**, with **regularization** keeping the pool diverse and decay-resistant. The literal formula library is the least important part.
1. **Data breadth & slowness** — fundamental/news/sentiment fields produce *higher fitness, lower turnover, and uncorrelated returns* (the things BRAIN actually scores).
2. **Diversity / originality enforcement** — crowded signals decay; uncrowded ones pay. This is now a first-class mechanism in SOTA systems, not an afterthought.
3. **Overfitting discipline** — deflated, multi-trial-aware scoring is what separates a real alpha from a backtest artifact.
## Prioritized upgrade roadmap
<table fit-page-width="true" header-row="true">
<tr>
<td>#</td>
<td>Upgrade</td>
<td>Why it matters</td>
<td>Where</td>
<td>Impact / Effort</td>
</tr>
<tr>
<td>1</td>
<td>Add explicit **Fitness gate** (WQ formula)</td>
<td>BRAIN's own threshold is fitness ≥ 1.0 (delay-1); you currently gate Sharpe but not fitness</td>
<td>\<code\>[config.py](http://config.py)\</code\>, \<code\>[orchestrator.py](http://orchestrator.py)\</code\></td>
<td>High / Low</td>
</tr>
<tr>
<td>2</td>
<td>**Bias seeding toward slow + alternative data** (fundamental, news, sentiment, relationship)</td>
<td>Lower turnover → higher fitness; uncorrelated returns → higher portfolio score</td>
<td>\<code\>[config.py](http://config.py)\</code\>, \<code\>llm_seed_[generator.py](http://generator.py)\</code\></td>
<td>High / Low</td>
</tr>
<tr>
<td>3</td>
<td>**Frequent Subtree Avoidance** on the winner pool</td>
<td>Prevents formulaic homogenization; forces exploration of un-crowded motifs</td>
<td>\<code\>llm_seed_[generator.py](http://generator.py)\</code\>, \<code\>[orchestrator.py](http://orchestrator.py)\</code\></td>
<td>High / Med</td>
</tr>
<tr>
<td>4</td>
<td>Replace string-similarity dedup with **AST subtree-isomorphism similarity**  • originality vs a crowded-alpha zoo</td>
<td>Real structural dedup; reject signals too close to public/known alphas</td>
<td>\<code\>syntax_[validator.py](http://validator.py)\</code\>, \<code\>oos_[deflation.py](http://deflation.py)\</code\></td>
<td>Med / Med</td>
</tr>
<tr>
<td>5</td>
<td>**Dimension-targeted refinement**</td>
<td>Spend branches fixing the alpha's actual weakness (turnover vs Sharpe vs corr) instead of a fixed tier order</td>
<td>\<code\>[orchestrator.py](http://orchestrator.py)\</code\></td>
<td>Med / Med</td>
</tr>
<tr>
<td>6</td>
<td>**Overfitting-Risk score** (IS–OOS gap) + optional PBO/CSCV portfolio check</td>
<td>Generalization gap widens with formula depth; catch it explicitly before submitting</td>
<td>\<code\>oos_[deflation.py](http://deflation.py)\</code\></td>
<td>Med / Med</td>
</tr>
<tr>
<td>7</td>
<td>**Submission diversification**  • marginal-contribution basket selection</td>
<td>BRAIN rewards uncorrelated baskets; concentration caps avoid wasted submissions</td>
<td>\<code\>submit_to_[worldquant.py](http://worldquant.py)\</code\></td>
<td>Med / Low</td>
</tr>
</table>
## The upgrades in detail
### 1. Gate on Fitness, not just Sharpe
BRAIN's score is driven by **Fitness = sqrt(abs(Returns) / max(turnover, 0.125)) × Sharpe**, and the documented submission bar is **Fitness ≥ 1.0 and Sharpe ≥ 1.25 for delay-1** (higher for delay-0: Sharpe \> 2, Fitness \> 1.3). Your promotion gate currently checks Sharpe, turnover, and self-correlation — but not fitness directly. A high-Sharpe / high-turnover alpha can still fail the fitness bar.
- Add `MIN_FITNESS = 1.0` (and a stricter delay-0 variant) to `config.py`.
- Compute the WQ fitness in the promotion block of `_evaluate_population` and add it as a hard gate + as a fail-reason feeding experience memory.
### 2. Bias seeding toward slow & alternative data
The single clearest empirical signal from real BRAIN results: **fundamental data → \~2.0 Sharpe at \~25% turnover, 1.26 fitness**, and reading fundamentals faster pushed that to **2.58 Sharpe / 1.70 fitness**. News + social-buzz signals added *uncorrelated* returns that lifted the overall (portfolio) score even when individual Sharpe was modest.
- You already group fields (`price / volatility / macro / size / fundamental / sentiment / momentum / relationship`). Add `SEED_FIELD_GROUP_WEIGHTS` that over-samples `fundamental`, `sentiment`, `relationship`, and `macro` relative to pure `price`/`momentum`.
- Wire those weights into the grammar engine's field selection (and into the LLM prompt's data-dictionary section) so the *default* population leans slow + uncorrelated.
- Rationale: lower turnover directly raises fitness, and slow data is structurally less crowded.
### 3. Frequent Subtree Avoidance (FSA)
The Alpha-Jungle MCTS work mines the **top-k most frequent subtrees among *effective* alphas (k = 3)** and explicitly instructs the generator to avoid them, which measurably improves diversity and downstream performance. You already steer *away from failures* (experience memory) — this is the success-side complement: steer away from *over-used winning motifs* so the pool doesn't collapse onto one structure.
- Maintain a rolling frequency count of subtrees across the winner pool.
- Penalize the top-3 subtrees during seed fill and during GA mutation (down-weight, don't hard-ban).
- Pairs naturally with the diversity gate (keep max pairwise correlation \< \~0.8).
### 4. AST similarity instead of a string proxy
You flagged `NEAR_DUPLICATE_SIMILARITY` as a cheap string proxy. SOTA originality enforcement parses each expression to an **AST and measures the largest common subtree (structural isomorphism)** to score similarity. Two upgrades:
- Use AST similarity for de-duplication (catches `rank(a/b)` ≈ `rank(b/a)`-type structural twins a string compare misses).
- Add an **originality check against a "crowded" zoo** — and this is the *correct* use of the 101 Formulaic Alphas: not as seeds, but as an **anti-target set** to reject structures that have already been arbitraged.
### 5. Dimension-targeted refinement
Your refinement is a fixed tier order (settings → windows → wraps). The MCTS work refines by **stochastically selecting the weakest scoring dimension** (softmax over `(e_max − e_i)/T`, T≈1) and directing the edit there. Translate to your gates:
- **Turnover too high** → increase decay / use slower data / lengthen windows.
- **Sharpe too low** → operator wraps, normalization, conditioning.
- **Correlation too high** → swap fields or the offending subtree.
This spends your `REFINE_MAX_BRANCHES` budget where it actually unblocks promotion.
### 6. Overfitting-risk score + portfolio-level PBO
Empirically, as refinement deepens a formula, **IS RankIC keeps rising while the IS–OOS gap widens** — the textbook overfitting signature. Your DSR already counts every trial (including refinement branches), which is exactly right. Add:
- An explicit **IS–OOS generalization-gap penalty** so deep, curve-fit branches are demoted even if IS looks great.
- Optionally, a **CSCV-based Probability of Backtest Overfitting (PBO)** check on the final basket before submission — the canonical guard against "a strategy that always looks good after enough trials."
### 7. Submission diversification & basket selection
BRAIN aggregates scores so that **uncorrelated baskets are rewarded**, and the docs advise **≤ 30% of submissions in any one (Region, Delay, Data-Category) intersection** and **≥ 5% delay-0**. You already compute orthogonal fitness — make it the *primary* objective for choosing the final basket (greedy max-marginal-contribution, i.e. add the alpha that least correlates with those already chosen), and encode the concentration caps in `submit_to_worldquant.py`.
## What you're already doing right (keep it)
- **Hybrid grammar + optional LLM** — matches the proposer/evolver consensus.
- **Experience memory (failure feedback)** — matches AlphaAgent's closed-loop refinement.
- **DSR with full trial counting + corrected (excess) kurtosis** — matches Bailey & López de Prado.
- **Parsimony depth penalty** — matches complexity-control regularization.
- **NSGA-II + orthogonal fitness** — matches the "mine a synergistic *set*, not lone alphas" insight.
- **Inline refinement of promoted winners** — this *is* the Warm-Start GP idea: lock a good structure and search the small, finite space around it.
## Suggested starting values
<table fit-page-width="true" header-row="true">
<tr>
<td>Knob</td>
<td>Suggested</td>
<td>Source / reasoning</td>
</tr>
<tr>
<td>MIN_FITNESS (delay-1)</td>
<td>1.0</td>
<td>BRAIN submission bar</td>
</tr>
<tr>
<td>MIN_FITNESS (delay-0)</td>
<td>1.3</td>
<td>BRAIN submission bar</td>
</tr>
<tr>
<td>FSA top-k subtrees to avoid</td>
<td>3</td>
<td>Alpha-Jungle MCTS</td>
</tr>
<tr>
<td>Max pairwise correlation (diversity)</td>
<td>≤ 0.7–0.8</td>
<td>your 0.70 self-corr gate is already in range</td>
</tr>
<tr>
<td>Seed field-group weighting</td>
<td>over-sample fundamental / news / relationship</td>
<td>real BRAIN fitness/turnover evidence</td>
</tr>
<tr>
<td>Submission concentration cap</td>
<td>≤ 30% per Region×Delay×Category; ≥ 5% delay-0</td>
<td>BRAIN docs</td>
</tr>
</table>
## Sources
- [Warm-Start Genetic Programming for alpha mining (initialization + structural constraints)](https://arxiv.org/abs/2412.00896)
- [Navigating the Alpha Jungle — LLM + MCTS, Frequent Subtree Avoidance, multi-dimensional scoring](https://arxiv.org/html/2505.11122v2)
- [AlphaAgent — regularized exploration: AST originality, complexity control, hypothesis alignment](https://arxiv.org/html/2502.16789v2)
- [Generating Synergistic Formulaic Alpha Collections via RL (AlphaGen)](https://arxiv.org/abs/2306.12964)
- [AlphaForge — generative-predictive mining + dynamic combination](https://arxiv.org/abs/2406.18394)
- [The Deflated Sharpe Ratio (Bailey & López de Prado)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [The Probability of Backtest Overfitting / CSCV](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- [WorldQuant IQC writeup — fitness formula, reversion, fundamental/news evidence (J. Glazar)](https://jglazar.github.io/projects/wq_project/)
- [WorldQuant BRAIN alpha documentation — submission thresholds & concentration rules](https://www.scribd.com/document/728780335/World-Quant-Brain-Alpha-Documentation)
\</content\>