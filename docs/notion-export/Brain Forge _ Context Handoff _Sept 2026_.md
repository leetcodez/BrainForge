<callout icon="📋">
	**Read this first.** Complete state of the Brain Forge project as of 4 Sep 2026 — written for the workspace migration so a fresh session (human or AI) can resume with zero lost context. Source of truth for code: the Brain Forge hub. Source of truth for direction: this doc + the deep-research doc.
</callout>
## Current override — offline implementation release
<mention-date start="2026-10-02"/>: the second lead-quant deep pass is implemented and validated as a versioned source overlay, not deployed or pushed to GitHub. Start with <mention-page url="https://app.notion.com/p/6a758724d8824e029b0892642dcc79df"/> for the full research report, code ZIP, two baseline-specific patches, tests, reproducible uncertainty evidence and unchanged recorded catalog. The first release remains preserved as its baseline.
**User direction: no more BRAIN pilots.** Use existing recorded evidence. Do not treat the September instructions in §4 or §10 as authorization for new scraping, platform probes, simulations, submissions or prompt-challenge work. The prior roadmap and platform figures below are historical context.
The v2 release passed 136 network-blocked tests, 10,000 genetic-output checks and 54 recorded-catalog smoke checks; both baseline patches were applied and byte-matched to the release. It adds semantics-preserving identity, durable attempt recovery/quarantine, bounded retries/budgets, measured basket redundancy, conditional HAC/bootstrap and fixed-pool CSCV diagnostics, and stable holdout-exposure tracking. No real platform calls ran. Synthetic uncertainty tests show bandwidth sensitivity and undercoverage, not calibrated alpha confidence. No historical campaign DB or verified normalized return panel was supplied. Financial efficacy, full catalog completeness, verified theme attribution and current alpha readiness remain unestablished. Individual code-mirror pages remain historical; merge the overlay only into a matching checkout while preserving DBs, checkpoints and attempt ledgers. Offline migration remains copy/rescore into a new empty destination.
## TL;DR
- WorldQuant BRAIN **Research Consultant** status is unlocked. Brain Forge = autonomous alpha-mining pipeline: harvest → seed → evolve → refine → decorrelate → submit.
- The engine is strong; **reach** is the bug — it searches **0.098%** of the 122,748-field catalog and optimizes a proxy of the platform's **old** scoring function.
- **Consultant-generator offline implementation release is complete** — <mention-page url="https://app.notion.com/p/30e900b2367f4d4093317a95a0e16d05"/>. Not merged into GitHub or deployed; the September roadmap below is retained as history.
- Platform scrape: merged catalog built (122,748 fields, 383 datasets); a **full re-snapshot with the patched script is still pending** (the old run silently under-scraped 6 of 10 regions).
- Prompt challenge: entry #1 fully drafted + validated, **paused pre-submission**.
- Believed **7–8 genuinely submittable alphas** exist from prior runs; [submission_scout.py](https://app.notion.com/p/2891e0f400914934954a0094a20fd2f4) ranks them — its new-metrics patch must be verified first (see §4).
## 1. What Brain Forge is
Autonomous alpha generator for the WorldQuant BRAIN platform. Repo: [leetcodez/BrainForge](https://github.com/leetcodez/BrainForge), branch main. Pipeline:
1. **Harvest** — [field_harvester.py](https://app.notion.com/p/2a4b873906d649ea8592bba4ff790c9e) ranks data fields (value/maturity/coverage/history/simplicity × crowding) and builds seed templates; [platform_snapshot.py](https://app.notion.com/p/c093eb836d324e33853e24516a3fac62) scrapes the full API catalog.
2. **Seed** — [llm_seed_generator.py](https://app.notion.com/p/0c1f9f6c550d4d579241b2ab59644766) + [inject_seeds.py](https://app.notion.com/p/66986a874c1c47f2954b9b6a7363b4f5) prime the population.
3. **Evolve** — [orchestrator.py](https://app.notion.com/p/983caefecdbd4f7db679b8fecf2e92f3): NSGA-II genetic engine (objectives: fitness, turnover), mutation/crossover, refinement loops, skeleton & field-diversity caps, deflated-Sharpe deflation via [oos_deflation.py](https://app.notion.com/p/87b025184bb6436792ce61f96a8dd38f).
4. **Select** — [decorrelation_selector.py](https://app.notion.com/p/e7b2436dd9994dbfb4048e108c340cc9) (return-based selection, currently OFF), [surrogate_prescreener.py](https://app.notion.com/p/ebf3b896018a4d398b62627ee3f57faf) (shadow mode).
5. **Submit** — [submission_scout.py](https://app.notion.com/p/2891e0f400914934954a0094a20fd2f4) ranks uncorrelated high-Sharpe candidates against BRAIN's gates; [submit_to_worldquant.py](https://app.notion.com/p/a3de589515234786872d03216ca5606a) submits.
## 2. Status snapshot (4 Sep 2026)
<table header-row="true">
<tr>
<td>Area</td>
<td>State</td>
<td>Where</td>
</tr>
<tr>
<td>Generator code</td>
<td>Stable, runs; pre-upgrade architecture</td>
<td>Brain Forge hub</td>
</tr>
<tr>
<td>Upgrade research</td>
<td>✅ Complete — 14 findings + P0/P1/P2 roadmap</td>
<td>Deep-research doc</td>
</tr>
<tr>
<td>Upgrade implementation</td>
<td>Implemented source overlay; offline validation passed; not deployed</td>
<td><mention-page url="https://app.notion.com/p/30e900b2367f4d4093317a95a0e16d05"/></td>
</tr>
<tr>
<td>Platform data scrape</td>
<td>⚠️ Merged catalog OK (122,748 fields); patched script ready; full v3 re-snapshot pending</td>
<td>§6 artifacts</td>
</tr>
<tr>
<td>Submission scouting</td>
<td>⚠️ Built; new-metrics patch unverified</td>
<td>§4 final note</td>
</tr>
<tr>
<td>Prompt challenge</td>
<td>⏸️ Paused — entry #1 ready to submit</td>
<td>§8</td>
</tr>
<tr>
<td>Earnings4 dedicated miner</td>
<td>❌ Scrapped (platform expanded 5×; general crawler replaced it)</td>
<td>hub (history)</td>
</tr>
<tr>
<td>KOLA</td>
<td>Separate project (HRMS RAG) — not part of this bundle</td>
<td>—</td>
</tr>
</table>
## 3. The 14 upgrade findings (summary)
Diagnosis in one line: **a well-built search algorithm pointed at 0.1% of the search space, optimizing a proxy of the platform's old scoring function.**
1. **Catalog bottleneck (biggest win).** HARVEST_VOCAB_MAX_FIELDS=120 → engine sees 120 of 122,748 fields (0.098%; 0.54% of the USA frontier). Fix = two-tier vocabulary: large ranked candidate pool + rotating \~300–800 active set. Do NOT just raise the cap — the mutation pool is the same dictionary, so mutation locality collapses into a random walk.
2. **Pyramid multiplier invisible to the ranker.** priorityScore has no multiplier term. Fix: multiply by pyramidMultiplier\^γ and add wq_fitness × pyramidMultiplier as a third NSGA-II objective.
3. **Region monoculture.** DEFAULT_REGION=USA hardcoded; EUR (39,039 fields, 13,399 frontier) untouched. Fix: region as first-class sweep axis + offline pre-flight validation of field availability from the catalog's per-field regions.
4. **Delay-0 untouched and disproportionately valuable.** USA delay-0 frontier density 82.5% vs 24.4% for delay-1. Bar is stricter (fitness ≥ 1.3) but payoff higher; SUBMISSION_MIN_DELAY0_FRACTION exists but is never enforced.
5. **VECTOR fields (26,536; 21.6% of catalog) viewed through one of seven operators.** Engine only emits vec_avg. vec_stddev/vec_avg = analyst-disagreement (coefficient of variation) — an entire signal family the engine cannot express today. Add a vector-projection mutation.
6. **2,939 GROUP fields excluded as signals but never used as neutralization keys.** 1,891 USA grouping keys vs 4 hardcoded neutralizations — the cheapest decorrelation lever available. Fix: separate GROUP_KEYS pool feeding neutralization mutation.
7. **New scoring gates not in the objective.** 2-year Sharpe (≥1.58), PnL realization (≥20), pyramid multiplier. is.checks catches FAILs but nothing optimizes for them. Add recency + realization refinement dimensions with their own neighbor generators.
8. **Decay grid skips the fast end.** Engine: \[0,5,10,15,20\]. Platform: 0,1,2,3,5,10,15,20 — the options/vol/event sweet spot is 1–3.
9. **Universe grid = 4 of 18.** MINVOL1M / ILLIQUID_MINVOL1M / TOPDIV3000 / TOPSP500 etc. are structurally different cross-sections = naturally decorrelated alphas.
10. **Throughput is binding; surrogate is off.** MAX_CONCURRENT_SIMULATIONS=3. Answer is sample efficiency, not throughput: surrogate as soft prioritizer (rank, don't block) + Thompson-sampling bandit over (dataset × family × template-class). Probe multi-sim batching.
11. **Mutation neighborhoods semantically wrong at scale.** Field mutation swaps within 8 coarse static groups. Use catalog dataset/category/subcategory; exploit 2,309 sibling families, 5,797 adjacent term-structure spread pairs (harvester caps at 40), and 426 complete semantic pairs (long/short, buy/sell).
12. **Return-based decorrelation selection is OFF.** AST similarity ≠ what BRAIN rejects on. Enable RETURN_DECORR_SELECTION; add Meucci ENB as a run-level metric; treat correlation budget as a portfolio constraint during search.
13. **Model-category exclusion is now backwards.** The highest-multiplier, least-crowded datasets are exactly the excluded ones: chart_cnn_alpha (764 frontier fields, 1.8×, 0.1 avg alphas), ai_equity_alpha, mmp_nlp_sentiment, ml_factor_proj. Include with a within-family correlation budget.
14. **Statistical honesty at 10⁵ scale.** DEFLATION_MAX_TRIALS=1000 is optimistic once vocabulary grows 100×; count effectively independent trials (cluster by AST motif / field family); the engine has no true holdout.
Full evidence, code references, and literature (Bailey & López de Prado DSR/PBO, Meucci ENB, AlphaGen/AlphaForge/AlphaAgent, warm-start GP): [Generator Upgrade — Deep Research (Sept 2026)](https://app.notion.com/p/ffd02679486c40459cbcde73fcb23cc1).
## 4. Agreed roadmap
**P0 — do first, in order:**
1. Re-run the platform snapshot with the patched script: run `python patch_snapshot.py`, then `python platform_snapshot.py --out snapshot_v3`, then verify `_completeness.json` shows complete: true AND all 10 regions in regions_with_rows (expect \~250k+ unique fields).
2. Two-tier vocabulary in field_[harvester.py](http://harvester.py) (candidate pool + rotating active set).
3. Pyramid-aware ranking: multiplier term in priorityScore + third NSGA-II objective.
4. Axis expansion: region (USA+EUR first), delay \{0,1\} with enforced delay-0 fraction, decay fast end \{1,2,3\}, wider universe grid.
5. Vector projection family (all 7 vec_\* operators; add the disagreement-ratio template).
6. GROUP_KEYS pool feeding neutralization mutation; probe group_vector_neut.
**P1:** surrogate soft-prioritizer + bandit arms; recency/realization refinement dimensions; return-decorrelation selection + ENB; Model-category re-inclusion with within-family correlation budget.
**P2:** effective-trials deflation fix; true holdout; multi-sim batching probe; optional --full-stats exhaustive stats matrix (\~1.1M rows).
**Also pending:** verify submission_[scout.py](http://scout.py) actually carries the new-metrics patch (raw check-payload preservation, 2Y-Sharpe / PnL-realization / pyramid extraction, Tier-A ranking by fitness × pyramid, NEW/UNKNOWN checks section, WARNING non-blocking) — a prior session claimed it landed but the page showed the original.
## 5. BRAIN platform knowledge base
**Scoring / submission gates (verified from live check output):**
- Sharpe ≥ 1.58 (example pass: 2.35); **2-year Sharpe ≥ 1.58** (recency gate)
- **PnL realization ≥ 20** for high-turnover alphas (example fail: 13)
- Pyramid theme multiplier: USA/D1/EARNINGS = 1.3×; catalog max 2.0 (fund_holdings_panel: herfindahl_index_holdings, holder_account_total, holding_value_distribution_score)
- fitness = sqrt(\|returns\| / max(turnover, 0.125)) × Sharpe
- Prompt-challenge limits: ≤ 50 active prompts, ≤ 50 submissions/day, \~50 names per prompt, ≥ 500 collective
**Catalog (merged snapshot):** 122,748 fields · 383 datasets. Regions: USA 85,406 · EUR 39,039 · ASI 24,794 · CHN 11,963 · HKG/IND/KOR/GLB \~10k each (capped artifacts — lower bounds) · MEA 2,112. Types: MATRIX 93,236 · VECTOR 26,536 · GROUP 2,939 · SYMBOL 21 · UNIVERSE 16. Frontier (multiplier ≥1.5, ≤50 alphas, coverage ≥0.5): 38,661 fields across 199 datasets (USA 22,289 · EUR 13,399). Virgin high-multiplier USA fields (0 alphas, ≥1.8×): 2,359 — top: analyst10 (794), ai_equity_alpha (290).
**Enums (new run):** 10 regions — ASI, CHN, DEU, EUR, GBR, GLB, HKG, IND, KOR, USA (DEU/GBR new, MEA absent from enum) · delays \{0,1\} · 18 universes — ILLIQUID_MINVOL1M, MINVOL10M, MINVOL1M, TOP200–TOP4000 family, TOP2000U, TOPCS1600, TOPDIV3000, TOPSP500 · 8 decays \{0,1,2,3,5,10,15,20\} · neutralizations \{INDUSTRY, MARKET, NONE, SUBINDUSTRY\} · statuses \{ACCEPTED, CONSULTANT_APPROVED, EXCLUDED, UNSUBMITTED\}.
**Operators:** 84 live — Time Series 30 · Arithmetic 16 · Logical 11 · Group 10 · Cross Sectional 7 · Vector 7 (vec_avg, vec_count, vec_max, vec_min, vec_range, vec_stddev, vec_sum) · Transformational 3. group_vector_neut and vec_choose are NOT in operators.json — probe before relying on them.
**Endpoints:** GET /alphas/\{id\} (is.checks) · /alphas/\{id\}/correlations/self · /alphas/\{id\}/recordsets/pnl · POST /alphas/\{id\}/submit · /users/self/alphas · /data-fields · /data-sets · /data-categories · /operators. Base: [https://api.worldquantbrain.com](https://api.worldquantbrain.com)
## 6. Artifacts — what lives where
**Inside this export bundle (travels automatically):** the whole codebase (42 pages, bifurcated on the hub) + all strategy docs. Key ones: [orchestrator.py](https://app.notion.com/p/983caefecdbd4f7db679b8fecf2e92f3), [config.py](https://app.notion.com/p/ef0f6e50acad401b806b9c675d6050df), [field_harvester.py](https://app.notion.com/p/2a4b873906d649ea8592bba4ff790c9e), [platform_snapshot.py](https://app.notion.com/p/c093eb836d324e33853e24516a3fac62), [submission_scout.py](https://app.notion.com/p/2891e0f400914934954a0094a20fd2f4), [Generator Upgrade — Deep Research](https://app.notion.com/p/ffd02679486c40459cbcde73fcb23cc1), [Alpha Generator — Research-Backed Upgrade Plan](https://app.notion.com/p/f75b2ff1e43a4b73a65d1ac33ca4dc29), [Architectural Flaws & Loopholes Audit](https://app.notion.com/p/36187d95344844de9530bb782f396543).
**Sandbox artifacts — ⚠️ do NOT transfer with a Notion workspace move; download before switching:**
- \[brain_fields_merged.json.xz\]([attachment\:9827fe2f-ebf7-47bb-98b0-427f15d1ed2f\:brain_fields_merged.json.xz](attachment:9827fe2f-ebf7-47bb-98b0-427f15d1ed2f:brain_fields_merged.json.xz)) — merged catalog, 122,748 fields (2.3 MB compressed → 78 MB)
- \[patch_[snapshot.py](http://snapshot.py)\]([attachment\:ace77f24-ad6a-401d-8931-4b602d876210\:patch_snapshot.py](attachment:ace77f24-ad6a-401d-8931-4b602d876210:patch_snapshot.py)) — patched crawler script (fixes the universe-axis gap)
- \[data_fields_unique.json.xz\]([attachment\:8c107426-42df-4573-bfee-fbcc5bdb68b1\:data_fields_unique.json.xz](attachment:8c107426-42df-4573-bfee-fbcc5bdb68b1:data_fields_unique.json.xz)) — deduped field export from the narrow snapshot
**External:** repo mirror at [github.com/leetcodez/BrainForge](https://github.com/leetcodez/BrainForge) (main).
## 7. Config knobs — current vs P0 target
<table header-row="true">
<tr>
<td>Knob ([config.py](http://config.py) / field_[harvester.py](http://harvester.py))</td>
<td>Now</td>
<td>P0 target</td>
</tr>
<tr>
<td>HARVEST_VOCAB_MAX_FIELDS</td>
<td>120</td>
<td>Two-tier: ranked candidate pool + rotating \~300–800 active set</td>
</tr>
<tr>
<td>HARVEST_VOCAB_PER_CATEGORY</td>
<td>20</td>
<td>Bandit-allocated from candidate pool</td>
</tr>
<tr>
<td>DECAYS</td>
<td>\[0,5,10,15,20\]</td>
<td>\[0,1,2,3,5,10,15,20\]</td>
</tr>
<tr>
<td>UNIVERSES</td>
<td>TOP3000/1000/500/200</td>
<td>Weighted across all 18</td>
</tr>
<tr>
<td>DEFAULT_DELAY</td>
<td>1</td>
<td>Sweep \{0,1\}; enforce SUBMISSION_MIN_DELAY0_FRACTION</td>
</tr>
<tr>
<td>DEFAULT_REGION</td>
<td>USA</td>
<td>Sweep USA + EUR first, then ASI</td>
</tr>
<tr>
<td>SEED_EXCLUDE_CATEGORIES</td>
<td>\[Model\]</td>
<td>\[\] — with within-family correlation budget</td>
</tr>
<tr>
<td>SEED_EXCLUDE_TYPES</td>
<td>\[GROUP\]</td>
<td>Keep for signals; add GROUP_KEYS neutralization pool</td>
</tr>
<tr>
<td>SURROGATE_ENABLED</td>
<td>0 (shadow)</td>
<td>1 as soft prioritizer, after evaluate_prescreener FN check</td>
</tr>
<tr>
<td>RETURN_DECORR_SELECTION_ENABLED</td>
<td>0</td>
<td>1 + ENB run-level metric</td>
</tr>
<tr>
<td>DEFLATION_MAX_TRIALS</td>
<td>1000</td>
<td>Effectively-independent-trials count</td>
</tr>
<tr>
<td>MAX_CONCURRENT_SIMULATIONS</td>
<td>3</td>
<td>Probe /simulations batching</td>
</tr>
</table>
## 8. Prompt challenge state
- **Entry #1:** "Cash-Flow Forensics L/S — Real Earnings vs. Accrual Traps" · model: Claude · Monthly · weight 0.70.
- Sample output = validated 25-entry JSON (21 longs, 4 shorts), scores strictly in (−1, 1); schema = one object mapping ISIN+MIC key → score.
- Submission form fields: Prompt Name · Model · Model Version (≤100 chars) · Update Frequency · Weight 0.00–1.00 · Prompt ≤10,000 chars · Sample Output = the exact tested JSON.
- ⚠️ Paste **raw JSON** into the form — chat-rendered copies contain escaped pipes and braces that break parsing.
- **Next:** expand context priming (\~50 names / \~15 shorts), re-normalize, submit entry #1; then prompts #2–4.
- v1 prompt triggered model refusals; v2 fixed it with an explicit EXECUTION block — reuse that pattern for #2–4.
## 9. Hard-won gotchas (do not relearn)
- /data-fields **requires a universe filter** — omitting it silently empties 6 of 10 regions while _completeness.json still reports complete: true. Any completeness ledger must assert **positive coverage** (every region returned rows), not just absence of truncation.
- Notion canonicalization: avoid emitting the literal closing-brace-plus-bracket-plus-paren sequence inside code fences in Notion pages. platform_[snapshot.py](http://snapshot.py)'s page has 5 such broken _store_raw braces; do NOT attempt in-page "fixes" — they fail. Edit code semantically only.
- Programmatic reordering of hub child-page blocks is unreliable — don't reorder hub blocks via targeted edits.
- In raw data-fields slices, delay appears as BOTH string and int — normalize before sorting/joining.
- Raw data-fields files are shaped endpoint + slices(settings, count, rows) — NOT a flat results array.
- themes\[\] is empty on every field record — pyramid **theme membership** needs a separate endpoint we haven't scraped yet.
- Multi-sim batching on /simulations is a hypothesis to probe, not confirmed.
- Absolutist "verify EVERY figure or EXCLUDE" phrasing triggers model refusals on generation tasks — use the v2 EXECUTION-block pattern.
- Submission form needs raw JSON, not chat-escaped text.
## 10. How to resume (paste into a fresh session)
> You are continuing Brain Forge, my autonomous WorldQuant BRAIN alpha generator (Research Consultant account). The full codebase lives under the "Brain Forge" hub page, each file on its own page; read the Context Handoff and "Generator Upgrade — Deep Research (Sept 2026)" first. Immediate next actions: (1) confirm I ran patch_[snapshot.py](http://snapshot.py) then platform_[snapshot.py](http://snapshot.py) --out snapshot_v3, and that _completeness.json shows complete: true with all 10 regions in regions_with_rows; (2) implement the P0 upgrade — two-tier vocabulary, pyramid-aware ranking, region/delay/decay/universe axis expansion, vector projections, GROUP neutralization keys — per the research doc; (3) verify submission_[scout.py](http://scout.py) carries the new-metrics patch, then run it to rank my 7–8 submittable alphas; (4) resume the prompt challenge from §8 of the handoff. Treat the handoff's gotchas section as binding; don't re-ask settled questions.