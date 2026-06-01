# Gen-2 Alpha Factory

An autonomous, mathematically rigorous Quantitative Signal Generator engineered for the WorldQuant Brain platform.

## Architecture

The Gen-2 Alpha Factory pivots away from naive "brute force" text combination and utilizes compiler-grade structural evolution to discover high-Sharpe trading signals. 

1.  **Seed Generation (`llm_seed_generator.py`)**: Utilizes Google's Gemini LLM (via `google-generativeai`) to rapidly generate JSON arrays of foundational mathematical structures (e.g., Mean Reversion, Volatility-Adjusted Momentum) using `FastExpr`.
2.  **Compiler-Grade AST Mutations (`orchestrator.py`)**: The `GeneticEngine` parses FastExpr strings directly into Python Abstract Syntax Trees (AST). To breed new alphas, it surgically grafts AST sub-trees (Crossover) and strictly swaps structurally equivalent nodes based on Data Dictionaries, guaranteeing 100% syntactically valid offspring.
3.  **Spatial Memory Vector DB**: Employs `scikit-learn` `TfidfVectorizer` to map the multi-dimensional search space of generated formulas. Offspring with >90% cosine similarity to previously failed formulas are instantly pruned locally, vastly reducing wasted API calls.
4.  **Pre-Flight Tautology Pruning (`syntax_validator.py`)**: An AST-based filter that scans for structurally bloated, zero-sum logic (e.g., `x/x` or `x-x`) before network submission.
5.  **Auto-Correlation Defense**: High-scoring alphas are submitted to WorldQuant's `/correlations/self` endpoint. Alphas with >0.70 correlation to the existing portfolio are automatically discarded to prevent spam penalties.
6.  **Stealth Network Layer (`network_engine.py`)**: Uses `curl_cffi` to impersonate browser fingerprints, handles complex API rate limits dynamically with exponential backoffs, and accurately routes live authentication cookies.

## Setup

1.  Create a Python 3.12 virtual environment: `python3 -m venv venv && source venv/bin/activate`
2.  Install dependencies: `pip install curl_cffi google-generativeai python-dotenv scikit-learn`
3.  Add your secrets to a local `.env` file (this file is `.gitignore`'d for safety):
```env
GEMINI_API_KEY="YOUR_API_KEY"
WQ_COOKIE="YOUR_WORLDQUANT_SESSION_COOKIE"
```
4.  Run the engine: `python3 orchestrator.py`