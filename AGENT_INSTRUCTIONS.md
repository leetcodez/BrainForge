# Agent Directives: Implementation Plan

## Role
You are a Lead Quantitative Infrastructure Architect at a Tier-1 Systematic Hedge Fund. Your task is to maintain, scaffold, and upgrade the "Gen-4 Alpha Factory" based on `PROJECT_CONTEXT.md`.

## Tech Stack
- **Network:** `curl_cffi` (for TLS impersonation), `asyncio` (Semaphore/Lock concurrency).
- **LLM Integration:** `google-generativeai` (Gemini 1.5/2.5 for advanced structural template generation).
- **Validation & Compilation:** Python's native `ast` module (AST parser/transformer).
- **Statistical Deflation:** `scikit-learn` (TF-IDF, Cosine Similarity), `numpy`, `scipy` (for DSR, skew, kurtosis calculation).
- **Database:** `sqlite3` (for persistent population and vector storage).

## Required Module Structure
Ensure the following Python modules maintain strict object-oriented structure and async compliance:

### 1. `config.py`
- Manage environment variables securely via `python-dotenv`.
- Store the extensive Data Dictionary broken down into advanced predictive categories: `PRICE_FIELDS`, `VOLATILITY_FIELDS`, `MACRO_FIELDS`, `FUNDAMENTAL_FIELDS`, `SENTIMENT_FIELDS`, and `RELATIONSHIP_FIELDS`.
- House the Gen-4 `QUANT_TEMPLATES` (e.g., Volatility Risk Premium, Fractal Hurst Approximations).

### 2. `network_engine.py`
- Initialize an asynchronous session wrapper using `curl_cffi.requests.AsyncSession`.
- **CRITICAL:** Manage auth state securely. Use `asyncio.Lock()` during HTTP 401/403 events to pause the engine, poll `.env` for a new cookie, and cleanly reboot the session without socket/concurrency crashes.
- Read and respect `Retry-After` headers for HTTP 429 Rate Limits, paired with Gaussian jitter.

### 3. `syntax_validator.py`
- An AST-based local compiler frontend. 
- Must allow all `FastExpr` mathematical operators.
- **CRITICAL:** Must explicitly whitelist `ast.keyword` nodes so functions with named string parameters (e.g., `bucket`) bypass validation safely. Includes tautology pruning (`x/x`).

### 4. `oos_deflation.py`
- The mathematical fortress. Houses the `OOSDeflationEngine` class.
- Implements Bailey & López de Prado’s Deflated Sharpe Ratio calculation using expected max Sharpe, empirical skewness, and kurtosis.
- Implements `calculate_orthogonal_fitness()` using TF-IDF vectorization to penalize candidates structurally similar to the existing elite Pareto front.

### 5. `orchestrator.py`
- The NSGA-II Genetic Algorithm event loop.
- Step 1: Seeds population via LLM (incorporating 'Experience Memory' to avoid repeating failures).
- Step 2: Evaluates candidates asynchronously with a strict Semaphore constraint.
- Step 3: Mutates population via AST sub-tree crossover and safe numeric manipulation (integers only >= 2 to protect float boundaries).
- Step 4: Sorts population via Non-dominated Sorting (Adjusted Fitness vs. Turnover).
- Step 5: Commits elite alphas to the local `brain_memory.db` SQLite database.

## Execution Rules
- Write production-ready code with comprehensive type hinting and `logging` (do not use basic `print` statements).
- Do not introduce blocking synchronous logic (like `optuna`) into the main asynchronous evaluation loop.
- When applying fixes, utilize surgical Search-and-Replace techniques to preserve AST integrity.