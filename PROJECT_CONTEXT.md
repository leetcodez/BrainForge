# Project Name: Project Brain-Forge (Gen-2 Alpha Factory)

## 1. System Overview
This project is an institutional-grade, fully automated quantitative research pipeline designed to mine cross-sectional equity alphas on the WorldQuant Brain platform. The system generates, mutates, validates, and simulates momentum and mean-reversion trading strategies autonomously.

## 2. The Target Platform (WorldQuant Brain)
- **Language:** The platform evaluates formulas using a proprietary language called `FastExpr`.
- **Execution:** Simulations are submitted via REST API (`/simulations`), and results are polled asynchronously.
- **Metrics:** A successful alpha must hit specific In-Sample metrics (Sharpe >= 1.25, Turnover <= 0.70, Fitness >= 1.0).

## 3. Core Architectural Constraints
The agent must design the system to respect these critical platform defenses:
- **Telemetry & Anti-Bot Evasion:** Standard Python HTTP requests are blocked via JA3/TLS fingerprinting. All network traffic MUST use `curl_cffi` impersonating a modern Chrome browser.
- **Rate Limiting:** Polling endpoints require Poisson/Gaussian distributed sleep delays (jitter) and strict adherence to `Retry-After` HTTP 429 headers.
- **Biometric Bypass:** The system does not use username/password authentication. It relies on a pre-extracted session JWT (`t=...`) injected directly into the session headers.
- **Syntax Strictness:** `FastExpr` is unforgiving. An Abstract Syntax Tree (AST) validation pass must occur locally before any formula is sent to the server to prevent API compilation errors.

## 4. The "Seed and Mutate" Paradigm
To preserve LLM token costs, the system does NOT ask the LLM to generate thousands of formulas. 
1. **Seed:** An LLM generates a single, structurally neutralized mathematical template using placeholders (e.g., `group_neutralize(ts_rank({FIELD}, 10), subindustry)`).
2. **Mutate:** A local Python engine hot-swaps `{FIELD}` with hundreds of local data dictionary metrics and simulates them in rapid succession.