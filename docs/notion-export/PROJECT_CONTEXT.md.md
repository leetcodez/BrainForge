# Project Name: Project Brain-Forge (Gen-4 Alpha Factory)
## 1. System Overview
This project is an institutional-grade, fully automated quantitative research pipeline designed to mine highly uncorrelated, cross-sectional equity alphas on the WorldQuant Brain platform. The Gen-4 architecture completely abandons basic price/volume momentum, pivoting to advanced non-linear feature engineering, Volatility Risk Premium (VRP), and alternative data (Supply Chain, NLP Sentiment). It autonomously generates, mutates, and validates signals utilizing an NSGA-II evolutionary algorithm.
## 2. The Target Platform (WorldQuant Brain)
- **Language:** The platform evaluates formulas using a proprietary language called `FastExpr`.
- **Execution:** Simulations are submitted via REST API (`/simulations`), and results are polled asynchronously.
- **Metrics:** A successful alpha must hit specific In-Sample metrics (Sharpe \>= 1.25, Turnover \<= 0.70, Fitness \>= 1.0).
## 3. Core Architectural Constraints
The agent must design the system to respect these critical platform defenses and quantitative boundaries:
- **Telemetry & Anti-Bot Evasion:** Standard Python HTTP requests are blocked via JA3/TLS fingerprinting. All network traffic MUST use `curl_cffi` impersonating a modern Chrome browser.
- **Dynamic Authentication:** The system uses a raw session cookie string (`WQ_COOKIE`). Due to frequent session expiries, the network engine MUST implement an `asyncio.Lock()` based Authentication Refresh Loop to prevent "Thundering Herd" race conditions when the cookie dies during concurrent simulations.
- **Rate Limiting & Concurrency:** Polling endpoints require strict `asyncio.Semaphore` throttling (max 5 concurrent tasks) combined with Gaussian distributed sleep delays to mimic human jitter.
- **Compiler-Grade Syntax Strictness:** `FastExpr` is unforgiving. An Abstract Syntax Tree (AST) validation pass must occur locally. The local compiler MUST permit `ast.keyword` nodes to allow complex continuous constraints (e.g., `bucket(x, range='0,1,0.1')`) while protecting them from destructive mutations.
## 4. The "Seed, Mutate, and Deflate" Paradigm
To combat multiple-testing bias and ensure Out-Of-Sample (OOS) survival, Gen-4 employs a rigorously penalized evolutionary loop:
1. **Seed:** An LLM generates structurally diverse mathematical templates targeting specific market anomalies (VRP, Cointegration, Entropy) utilizing granular placeholders (e.g., `{VOLATILITY}`, `{SENTIMENT}`, `{RELATIONSHIP}`).
2. **Mutate & Crossover:** A local Python engine dynamically hot-swaps placeholders with categorized local data dictionaries. It performs AST sub-tree grafting (crossover) and non-destructive constant mutation to breed offspring.
3. **Deflate & Force Orthogonality:** The architecture calculates a **Deflated Sharpe Ratio (DSR)** using the historical skew and kurtosis of the returns. It then applies **Orthogonal Spatial Forcing** (via TF-IDF vectorization) to penalize new alphas that are semantically correlated to existing winners, forcing the genetic algorithm to explore undiscovered mathematical subspaces.
---
## 5. Live Run Handoff — earnings4 (updated 2026-06-09)
<callout icon="🛰️" color="blue_bg">
	Snapshot of the active earnings4 run so a new chat can pick up instantly without re-reading the whole history.
</callout>
### Currently running
- **Process:** `orchestrator.py` in WSL (resumed run; survives terminal disconnect under `nohup`, but NOT a full WSL/VM crash).
- **Database:** `brain_memory.earnings4_run2.db`
- **Checkpoint:** `.wq_checkpoint.earnings4_run2.json`
- **Env vars that MUST be exported before any relaunch** (a WSL crash wipes shell exports → defaults silently point at the wrong DB/scope):
	- `WQ_DATASET_ID=earnings4`
	- `WQ_HARVEST_BACKFILL_WINDOW=252`
	- `WQ_CHECKS_GATE=1`
	- `BRAINFORGE_DB=brain_memory.earnings4_run2.db`
	- `WQ_CHECKPOINT=.wq_checkpoint.earnings4_run2.json`
- **Concurrency stays at 3** (`MAX_CONCURRENT_SIMULATIONS`) — raising it re-triggers 429 throttling.
- **Cookie refresh:** paste a fresh `WQ_COOKIE` into `.env` while the process is paused; it auto-detects and resumes within \~5s. No restart needed. The new `.env` cookie always wins over the cached `.wq_session.json`.
### State as of 2026-06-09 \~12:30
- Generations 0→2, **1112 alphas**, **45 qualified**, best Sharpe **2.43** (gen 2).
- Best *fitness* (0.4039, gen-0 seed) is **unsubmittable** — it's the concentrated shape that fails BRAIN's concentration check. Ignore the analyzer's "GA did NOT beat the seed" line; among *checks-passing* alphas the GA is clearly improving (best qualified Sharpe rose 1.74 → 2.35 across generations).
- Best Sharpe still climbing each gen (2.13 → 2.22 → 2.43) → **not yet plateaued**.
- Universe sweep barely started (still \~all TOP3000) → sub-universe upside still untapped.
- Structural diversity widening (multi-field 28% → 41%, turnover-gated 15% → 25%).
### Submission strategy (decided)
- **Not submitting yet.** Wait for the fitness plateau (best/mean fitness flat \~2–3 consecutive gens) AND for the universe sweep to mature.
- Rationale: everything is mined from one dataset → high intra-dataset correlation. Submitting a weak vol-sibling now would anchor the 0.70 self-correlation budget and block its stronger future cousin. Submissions are sticky/irreversible.
- **When ready:** submit *best-first*, and pick the best checks-passing alpha from each **distinct field family** (`fivehundred_day_close_to_close_vol`, `put_call_slope_28d`, `ninety_day_interpolated_implied_volatility`, `second_month_highest_strike_price`, `sixth_event_option_effect`, `atm_volatility_month3`, …) — NOT the top-10 by fitness (which are correlated vol siblings).
- **Before running the submitter:** add a fitness floor to `submit_to_worldquant.py` so negative-fitness candidates can't fill submission slots (the candidate query currently screens only on checks-pass + min turnover).
### Useful commands
```bash
# Full report (read-only; safe to run live)
python3 analyze_run.py --db brain_memory.earnings4_run2.db --top 40

# Per-generation progress / plateau check
sqlite3 brain_memory.earnings4_run2.db "SELECT generation, COUNT(*), ROUND(MAX(fitness),3) best_fit, ROUND(MAX(sharpe),2) best_shp FROM alpha_population WHERE fitness IS NOT NULL GROUP BY generation ORDER BY generation;"

# Has the universe sweep kicked in?
sqlite3 brain_memory.earnings4_run2.db "SELECT universe, COUNT(*) FROM alpha_population GROUP BY universe;"
```
### Code status
All fixes applied + verified across `orchestrator.py`, `config.py`, `db_manager.py` (added `failed_checks` column), `field_harvester.py` (backfill densification, window 252), `llm_seed_generator.py` (neutralization bias), and `submit_to_worldquant.py` (live checks guard). The checks gate (holds back BRAIN check-failing alphas from qualifying/submission) is the central safety mechanism and is working as intended.