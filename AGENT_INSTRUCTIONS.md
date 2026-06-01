# Agent Directives: Implementation Plan

## Role
You are a Senior Quantitative Developer and Infrastructure Architect. Your task is to scaffold and implement the "Gen-2 Alpha Factory" based on `PROJECT_CONTEXT.md`.

## Tech Stack
- **Network:** `curl_cffi` (Strict requirement for TLS impersonation), `asyncio`, `aiohttp` (for batching).
- **LLM Integration:** `google-generativeai` (Gemini 1.5 Flash for rapid template generation).
- **Validation:** Python's native `ast` module (to build a lightweight compiler frontend for FastExpr validation).

## Required Module Structure
Please generate the following Python modules in a modular, object-oriented structure:

### 1. `config.py`
- Manage environment variables (Gemini API key).
- Store the massive browser session cookie string.
- House the local Data Dictionary (a list of 50+ WorldQuant data fields like `close`, `vwap`, `fra_sales`, `returns`).

### 2. `network_engine.py`
- Initialize an asynchronous session wrapper using `curl_cffi.requests.AsyncSession(impersonate="chrome120")`.
- Implement `submit_simulation(expression)` and `poll_simulation(location_url)`.
- **CRITICAL:** Enforce Gaussian jitter (e.g., `random.gauss(5.5, 1.2)`) between all polling requests.
- **CRITICAL:** Implement a circuit breaker that catches `429 Too Many Requests` and reads the `Retry-After` header to pause the async loop.

### 3. `syntax_validator.py`
- Write a lightweight parser that takes an LLM-generated string and ensures balanced parentheses and valid FastExpr operators. 
- Ensure every expression contains a structural neutralization operator (e.g., `group_neutralize` or `group_rank`). If it doesn't, the module should automatically wrap the expression before passing it forward.

### 4. `llm_seed_generator.py`
- Formulate a strict system prompt instructing the LLM to output ONLY mathematical templates using `{FIELD}`, `{LOOKBACK_SHORT}`, and `{LOOKBACK_LONG}` placeholders.
- Focus the prompt on generating momentum and volatility-adjusted mean-reversion concepts.

### 5. `orchestrator.py`
- The main event loop. 
- Step 1: Call `llm_seed_generator` to get a template.
- Step 2: Pass the template through `syntax_validator`.
- Step 3: Loop through the `config` Data Dictionary, replacing `{FIELD}` to create a batch of 10-20 distinct formulas.
- Step 4: Dispatch the batch asynchronously via `network_engine`.
- Step 5: Log the Alphas that pass the > 1.25 Sharpe threshold to a local `winners.csv` file.

## Execution Rules
- Write production-ready code with comprehensive type hinting and `logging` (do not use basic `print` statements).
- Do not execute the code immediately; present the module files for review first.
- Ask me for the actual session cookie string once the scaffold is complete.