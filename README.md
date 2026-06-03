# BrainForge: Gen-4 Alpha Factory

BrainForge is an institutional-grade, fully automated quantitative research pipeline designed to mine highly uncorrelated, cross-sectional equity alphas on the WorldQuant Brain platform. Operating as a fully self-directed research agent, it continuously hypothesizes, tests, mutates, and validates predictive trading signals (alphas) using a rigorously penalized evolutionary architecture.

## Gen-4 Architecture

The Gen-4 release abandons basic price/volume momentum, pivoting to advanced non-linear feature engineering, Volatility Risk Premium (VRP), and alternative data (Supply Chain, NLP Sentiment). It employs a heavily fortified **"Seed, Mutate, and Deflate"** paradigm to ensure Out-Of-Sample (OOS) survival and combat multiple-testing bias.

### Core Systems

1. **Seed, Mutate, and Deflate Paradigm**
   - **Seed**: Gemini 1.5/2.5 generates structurally diverse mathematical templates targeting specific market anomalies (VRP, Cointegration, Entropy) using granular placeholders.
   - **Mutate & Crossover**: An AST-based local Python engine dynamically hot-swaps placeholders with categorized local data dictionaries, performing AST sub-tree grafting (crossover) and non-destructive constant mutation.
   - **Deflate**: Implements Bailey & López de Prado’s **Deflated Sharpe Ratio (DSR)** calculation using expected max Sharpe, empirical skewness, and kurtosis to harshly penalize overfit candidates.

2. **Orthogonal Spatial Forcing**
   - To force the genetic algorithm to explore undiscovered mathematical subspaces, Gen-4 uses TF-IDF vectorization and Cosine Similarity to calculate an **Orthogonal Fitness** multiplier. 
   - Candidates that are semantically correlated to existing elite alphas are heavily penalized, drastically reducing structural collinearity and maximizing portfolio diversification.

3. **Compiler-Grade AST Syntax Validation**
   - A local compiler frontend built with Python's native `ast` module strictly enforces `FastExpr` grammar.
   - It validates arity, prunes tautologies (e.g., `x/x`), structurally neutralizes expressions, and explicitly whitelists continuous constraint `ast.keyword` nodes from destructive mutations.

4. **High-Concurrency Asynchronous Execution**
   - The entire main loop runs asynchronously via `asyncio`.
   - **Network Engine**: Built on `curl_cffi` for TLS impersonation. Features strict `asyncio.Semaphore` throttling with Gaussian jitter.
   - **Authentication Lock**: Implements an `asyncio.Lock`-based refresh loop to safely reload session cookies mid-flight without "Thundering Herd" race conditions or dropped socket connections.
   - **NSGA-II**: Non-dominated Sorting Genetic Algorithm evaluates alphas in batches, sorting across Adjusted Fitness (DSR + Orthogonality - Parsimony penalty) vs. Turnover.

## Setup & Installation

1. Create a Python 3.12 virtual environment: 
   ```bash
   python3 -m venv venv && source venv/bin/activate
   ```
2. Install dependencies: 
   ```bash
   pip install -r requirements.txt
   ```
3. Add your secrets to a local `.env` file (excluded from version control):
   ```env
   GEMINI_API_KEY="YOUR_API_KEY"
   WQ_COOKIE="YOUR_WORLDQUANT_SESSION_COOKIE"
   ```
4. Run the autonomous agent: 
   ```bash
   python3 orchestrator.py
   ```
