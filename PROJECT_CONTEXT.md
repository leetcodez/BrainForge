# Project Name: Project Brain-Forge (Gen-4 Alpha Factory)

## 1. System Overview

This project is an institutional-grade, fully automated quantitative research pipeline designed to mine highly uncorrelated, cross-sectional equity alphas on the WorldQuant Brain platform. The Gen-4 architecture completely abandons basic price/volume momentum, pivoting to advanced non-linear feature engineering, Volatility Risk Premium (VRP), and alternative data (Supply Chain, NLP Sentiment). It autonomously generates, mutates, and validates signals utilizing an NSGA-II evolutionary algorithm.

## 2. The Target Platform (WorldQuant Brain)

- **Language:** The platform evaluates formulas using a proprietary language called `FastExpr`.
- **Execution:** Simulations are submitted via REST API (`/simulations`), and results are polled asynchronously.
- **Metrics:** A successful alpha must hit specific In-Sample metrics (Sharpe >= 1.25, Turnover <= 0.70, Fitness >= 1.0).

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