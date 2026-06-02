# BrainForge: Gen-3 Autonomous Alpha Discovery Agent

BrainForge is an autonomous, self-evolving Quantitative Signal Generator engineered for the WorldQuant Brain platform. Operating as a fully self-directed research agent, it continuously hypothesizes, tests, mutates, and validates predictive trading signals (alphas) using an institutional-grade evolutionary architecture.

## Gen-3 Architecture

The Gen-3 release marks a paradigm shift from traditional procedural generation to an LLM-guided, multi-objective evolutionary engine. It integrates compiler-grade structural analysis with advanced heuristic optimization to discover robust, high-Sharpe trading signals.

### Core Systems

1. **LLM-Driven Ralph Loop (Thoughts Decompiler)**
   At the heart of the Gen-3 architecture is the *Ralph Loop*—an LLM-driven cognitive framework that analyzes empirical performance data of generated signals. Using the Thoughts Decompiler, the agent reverse-engineers the mathematical intuition behind successful (and failed) alphas. It prompts the LLM to hypothesize structural improvements, allowing the system to learn from its search trajectory and intelligently bias future generation.

2. **AST-Aware Grammar-Guided Mutations**
   Moving beyond brute-force permutations, BrainForge leverages Python's Abstract Syntax Trees (AST) and the FastExpr grammar to perform structurally sound mutations. 
   - **Syntax Validity Guarantee**: By treating alphas as AST sub-trees, the engine conducts crossover and mutation operations that respect mathematical grammar.
   - **Smart Grafting**: Structurally equivalent nodes (mapped via Data Dictionaries) are dynamically swapped without breaking syntactical integrity.
   - **Pre-Flight Tautology Pruning**: An AST-based filter that scans for structurally bloated, zero-sum logic (e.g., `x/x` or `x-x`) prior to network submission, eliminating wasted API calls.

3. **NSGA-II Pareto Sorting for Multi-Objective Optimization**
   BrainForge evaluates alphas not just on Sharpe ratio, but across multiple dimensions of robustness (Returns, Drawdown, Turnover, Sub-Universe Performance). 
   - The evolutionary engine employs Non-dominated Sorting Genetic Algorithm II (**NSGA-II**) to maintain a diverse frontier of elite alphas.
   - By sorting candidate signals into Pareto fronts and applying crowding distance metrics, the system ensures a wide coverage of the mathematical search space, preventing premature convergence on local optima and significantly reducing over-correlation to existing strategies.

4. **Stealth Network Engine**
   A robust execution layer built on `curl_cffi` to accurately route live authentication cookies, simulate real browser fingerprints, and seamlessly navigate complex API rate limits with dynamic exponential backoffs.

## Autonomous Operation

BrainForge is designed to operate autonomously:
- It generates initial seeds via LLM context.
- Simulates them against WorldQuant Brain endpoints.
- Evaluates the results, decomposing failures and successes via the Ralph Loop.
- Evolves the population using AST-aware mutations and NSGA-II selection.
- Defends against over-correlation by automatically culling alphas too similar to the existing portfolio.

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
