# BrainForge Complete Codebase Export

This document contains the complete Gen-2 Alpha Factory architecture for WorldQuant Brain. It is structured for LLM Deep Research analysis.

## File: `README.md`
```markdown
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
```

## File: `config.py`
```python
import os
from dotenv import load_dotenv

load_dotenv()

# API Configurations
WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
WQ_COOKIE = os.getenv("WQ_COOKIE", "cookieyes-consent=consentid:MnNBbnljSThGUWJQRkFSaE5SNXd1WmdJZXpTY1c0RG4,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; __zlcmid=1XjoXQxrdKEmm6w; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJPTzlXOG91VUZoSXRIYXAxZ0Z0S0hMRFFWS2FhM042OCIsImV4cCI6MTc4MDM2MjMwMSwiYW1yIjpbInB3ZCIsImZhY2UiXX0.GJ-p7Wwgay82JLC31Y5_S_BgpaL66w9u4wdulwr4hpk")

# Data Dictionary (Categorized)
PRICE_FIELDS = ["close", "open", "high", "low", "vwap", "adv20", "after_session_vwap", "after_hours_vwap_2", "after_hours_vwap_value"]
FUNDAMENTAL_FIELDS = [
    "abnormal_return_earnings_release", "accrued_liabilities_total", "accrued_liabilities_total_2",
    "accumulated_amortization_customer_intangibles", "accumulated_amortization_customer_intangibles_2",
    "accumulated_amortization_finite_intangibles", "accumulated_depreciation_depletion_amortization_ppne",
    "accumulated_oci_net_of_tax_value", "acquired_cash_equivalents_business_combination",
    "acquired_finite_intangible_assets", "acquired_finite_intangible_assets_total", "acquired_goodwill_value",
    "acquired_intangible_avg_useful_life", "acquired_property_equipment_value", "acquisition_assets_property_plant_equipment",
    "acquisition_goodwill_amount", "acquisition_identifiable_assets_recognized", "acquisition_liabilities_assumed",
    "acquisition_proforma_revenue", "acquisition_related_costs_expense", "acquisition_related_expenses",
    "acquisition_total_purchase_price", "acquisition_total_purchase_value", "actual_cashflow_per_share_value_quarterly",
    "actual_dividend_value_quarterly", "actual_earnings_per_share_2", "actual_earnings_per_share_3",
    "actual_earnings_per_share_4", "actual_earnings_per_share_value", "actual_earnings_per_share_value_2_1555",
    "actual_earnings_per_share_value_afterhours", "actual_eps_value", "actual_eps_value_2", "actual_eps_value_quarterly",
    "actual_return_on_pension_plan_assets", "actual_sales_value_annual", "actual_sales_value_quarterly",
    "adj_net_income_avg", "adj_net_income_median", "adj_net_income_stddev"
]
MOMENTUM_FIELDS = ["volume", "returns", "adjfactor", "actuals_reporting_currency", "actuals_value_currency_code", "advantageous_position_flag", "advantageous_position_flag_pre_filter"]

# Flat list for fallback
DATA_DICTIONARY = PRICE_FIELDS + FUNDAMENTAL_FIELDS + MOMENTUM_FIELDS

# Hardcoded Quant Library Templates
QUANT_TEMPLATES = [
    # Mean Reversion on Fundamentals
    "group_neutralize(rank(-ts_zscore({FUNDAMENTAL}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # Fundamental to Price Ratio
    "group_neutralize(rank({FUNDAMENTAL} / {PRICE}), {NEUTRALIZATION})",
    # Volatility Adjusted Momentum
    "group_neutralize(rank(ts_decay_linear(ts_rank({MOMENTUM}, {LOOKBACK_SHORT}), {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # Price Reversion
    "group_neutralize(rank(ts_rank({PRICE}, {LOOKBACK_SHORT}) - ts_rank({PRICE}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # Cross-sectional Fundamental Momentum
    "group_neutralize(rank(ts_delta({FUNDAMENTAL}, {LOOKBACK_SHORT})), {NEUTRALIZATION})"
]

# Network Settings
BROWSER_IMPERSONATE = "chrome110" # curl_cffi impersonation string
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5

# LLM Configurations
LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# Mutation & Genetic Evolution Settings
POPULATION_SIZE = 50
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.2
TOURNAMENT_SIZE = 5

# Simulation Settings
DEFAULT_INSTRUMENT = "EQUITY"
DEFAULT_DELAY = 1
DEFAULT_DECAY = 15
DEFAULT_NEUTRALIZATION = "SUBINDUSTRY"
DEFAULT_TRUNCATION = 0.08

```

## File: `llm_seed_generator.py`
```python
import logging
import os
import time
import json
import google.generativeai as genai
import config
from typing import List, Dict

logger = logging.getLogger(__name__)

class LLMSeedGenerator:
    def __init__(self):
        self.model_name = config.LLM_MODEL
        genai.configure(api_key=config.GEMINI_API_KEY)
        
        self.system_prompt = (
            "You are a world-class quantitative analyst creating alphas for WorldQuant Brain using FastExpr. "
            "Your output must ONLY be a raw JSON array of strings, where each string is a distinct FastExpr mathematical formula template. "
            "Use {FIELD}, {LOOKBACK_SHORT}, and {LOOKBACK_LONG} placeholders. "
            "Focus on generating structural diversity (momentum, volatility-adjusted mean-reversion, statistical arbitrage). "
            "Available Operators: ts_mean, ts_rank, ts_std_dev, ts_zscore, ts_decay_linear, ts_sum, ts_product, rank, zscore. "
            "Do NOT use group operators like group_neutralize; they will be applied automatically by the orchestrator. "
            "Ensure the formulas are syntactically valid and mathematically sound."
        )
        
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.8,
                response_mime_type="application/json"
            )
        )

    def generate_seed_alphas(self, count: int) -> List[str]:
        """Generates an initial seed population of alphas in bulk via a single LLM request."""
        prompt = f"Generate an array of {count} highly distinct FastExpr templates. Return STRICTLY a JSON list of strings."
        
        for attempt in range(3):
            try:
                logger.info(f"Requesting bulk batch of {count} templates from Gemini (Attempt {attempt+1}/3)...")
                response = self.model.generate_content(prompt)
                
                if response.text:
                    raw_text = response.text.strip()
                    try:
                        seeds = json.loads(raw_text)
                        if isinstance(seeds, list):
                            logger.info(f"Successfully generated {len(seeds)} bulk templates in one API call.")
                            
                            # Log the templates
                            for i, seed in enumerate(seeds):
                                logger.info(f"Template #{i}: {seed}")
                                
                            # Basic Token Bucket Pacer (Strategy 3 fallback)
                            time.sleep(4.5) 
                            
                            return seeds
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        
            except Exception as e:
                logger.error(f"Gemini Generation failed: {e}")
                if "429" in str(e) or "Quota exceeded" in str(e):
                    logger.warning("Rate limit hit. Applying exponential backoff (30 seconds)...")
                    time.sleep(30)
                else:
                    time.sleep(5)
                    
        logger.warning("Failed to generate seeds after 3 attempts.")
        return []
```

## File: `syntax_validator.py`
```python
import ast
import re
import logging

logger = logging.getLogger(__name__)

class AlphaSyntaxValidator(ast.NodeVisitor):
    def __init__(self):
        # Whitelisted AST nodes for structural security
        self.allowed_nodes = {
            ast.Module, ast.Expression, ast.Expr, ast.Call, ast.Name, ast.Load,
            ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
            ast.USub, ast.UAdd, ast.Constant, ast.Attribute, ast.List
        }
        
        # Allowed operators in FastExpr
        self.allowed_operators = {
            'add', 'sqrt', 'log', 'subtract', 'signed_power', 'sign', 'reverse', 'power', 
            'multiply', 'min', 'max', 'inverse', 'densify', 'abs', 'divide', 'and', 'equal', 
            'or', 'not_equal', 'not', 'greater', 'greater_equal', 'less_equal', 'is_nan', 
            'if_else', 'less', 'ts_sum', 'ts_zscore', 'ts_std_dev', 'ts_mean', 'ts_scale', 
            'ts_rank', 'ts_quantile', 'ts_arg_min', 'ts_regression', 'kth_element', 'ts_corr', 
            'ts_count_nans', 'ts_covariance', 'ts_decay_linear', 'ts_product', 'ts_delay', 
            'ts_backfill', 'ts_av_diff', 'hump', 'ts_arg_max', 'last_diff_value', 'ts_step', 
            'ts_delta', 'days_from_last_change', 'winsorize', 'normalize', 'quantile', 'rank', 
            'scale', 'zscore', 'vec_sum', 'vec_avg', 'bucket', 'trade_when', 'group_scale', 
            'group_neutralize', 'group_zscore', 'group_backfill', 'group_mean', 'group_rank'
        }

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise ValueError(f"Forbidden AST node type: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.lower()
            if func_name not in self.allowed_operators:
                raise ValueError(f"Forbidden function call: {func_name}")
        self.generic_visit(node)

class SyntaxValidator:
    @staticmethod
    def is_tautology(expression: str) -> bool:
        """Upgrade #3: Pre-Flight Statistical Pruning. Discards mathematically bloated formulas (e.g. x/x)."""
        try:
            tree = ast.parse(expression, mode='eval')
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and type(node.op) in (ast.Div, ast.Sub):
                    if ast.unparse(node.left) == ast.unparse(node.right):
                        return True
            return False
        except Exception:
            return True

    @staticmethod
    def parse_and_validate(expression: str) -> bool:
        """Parses LLM output into AST and validates against allowed node types and operators."""
        try:
            # Basic deterministic auto-correction: simple regex replacements
            expression = SyntaxValidator._rectify_syntax(expression)
            
            # The ast.parse mode='eval' expects a single expression.
            tree = ast.parse(expression, mode='eval')
            validator = AlphaSyntaxValidator()
            validator.visit(tree)
            return True, expression
        except Exception as e:
            logger.error(f"Syntax validation failed for '{expression}': {e}")
            return False, expression

    @staticmethod
    def _rectify_syntax(expression: str) -> str:
        """Automatically resolves minor LLM syntax hallucinations (e.g., missing lookback parameters)."""
        # Convert standalone variables like ts_mean(close) -> ts_mean(close, 20) as an auto-correction example
        expression = re.sub(r'ts_mean\(\s*([a-zA-Z_0-9]+)\s*\)', r'ts_mean(\1, 20)', expression, flags=re.IGNORECASE)
        # Fix missing commas in ts_max(close 20) -> ts_max(close, 20)
        expression = re.sub(r'([a-zA-Z_0-9]+)\s+(\d+)', r'\1, \2', expression)
        return expression.strip()

```

## File: `network_engine.py`
```python
import asyncio
import time
import random
import logging
from typing import Dict, Any, Optional
from curl_cffi import requests

import config

logger = logging.getLogger(__name__)

class NetworkEngine:
    def __init__(self):
        self.session = requests.AsyncSession(
            impersonate=config.BROWSER_IMPERSONATE,
            headers={
                "Cookie": config.WQ_COOKIE,
                "Content-Type": "application/json"
            }
        )

    async def _gaussian_jitter(self):
        """Injects artificial Poisson-distributed/Gaussian sleep delays between API requests."""
        # Using a normal distribution to simulate human variation around a mean
        mean = (config.MAX_JITTER_SECS + config.MIN_JITTER_SECS) / 2
        std_dev = (config.MAX_JITTER_SECS - config.MIN_JITTER_SECS) / 4
        delay = max(config.MIN_JITTER_SECS, min(config.MAX_JITTER_SECS, random.gauss(mean, std_dev)))
        await asyncio.sleep(delay)

    async def _handle_rate_limit(self, response: requests.Response) -> bool:
        """Parses Retry-After headers to dynamically adjust asynchronous polling delays."""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else config.MAX_JITTER_SECS * 2
            logger.warning(f"Rate limited (429). Retrying after {delay} seconds.")
            await asyncio.sleep(delay)
            return True
        return False

    async def request(self, method: str, endpoint: str, json: Optional[Dict] = None, retry_count: int = 3) -> Dict[str, Any]:
        """Executes a stealth network request with dynamic retry and error handling."""
        url = f"{config.WQ_BASE_URL}{endpoint}"
        
        for attempt in range(retry_count):
            await self._gaussian_jitter()
            try:
                response = await self.session.request(method, url, json=json)
                
                if await self._handle_rate_limit(response):
                    continue
                
                if response.status_code >= 400:
                    logger.error(f"HTTP {response.status_code} Error: {response.text}")
                    response.raise_for_status()

                if not response.text.strip():
                    return {}
                    
                return response.json()
                
            except Exception as e:
                logger.error(f"Request failed: {url} - {e}")
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(config.MAX_JITTER_SECS)
                
        raise Exception(f"Failed to fetch {url} after {retry_count} attempts.")

    async def close(self):
        await self.session.close()

```

## File: `orchestrator.py`
```python
import asyncio
import logging
import random
import ast
import copy
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from network_engine import NetworkEngine
from syntax_validator import SyntaxValidator
from llm_seed_generator import LLMSeedGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class GeneticEngine:
    """Handles the Seed-and-Mutate framework using Compiler-Grade AST manipulations."""
    
    @staticmethod
    def mutate(expression: str) -> str:
        """Applies stochastic genetic mutation on AST nodes guaranteeing syntax validity."""
        if random.random() > config.MUTATION_RATE:
            return expression
            
        try:
            tree = ast.parse(expression, mode='eval')
            nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Constant, ast.Call))]
            
            if not nodes:
                return expression
                
            node = random.choice(nodes)
            
            if isinstance(node, ast.Name):
                # Smart typed mutation
                if node.id in config.PRICE_FIELDS:
                    node.id = random.choice(config.PRICE_FIELDS)
                elif node.id in config.FUNDAMENTAL_FIELDS:
                    node.id = random.choice(config.FUNDAMENTAL_FIELDS)
                elif node.id in config.MOMENTUM_FIELDS:
                    node.id = random.choice(config.MOMENTUM_FIELDS)
            elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                # Mutate temporal lookbacks safely
                node.value = random.choice([5, 10, 20, 60, 120, 250])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                # Mutate mathematical operator boundaries
                time_series_ops = ['ts_mean', 'ts_decay_linear', 'ts_std_dev', 'ts_zscore', 'ts_sum', 'ts_rank']
                if node.func.id in time_series_ops:
                    node.func.id = random.choice(time_series_ops)
                    
            ast.fix_missing_locations(tree)
            return ast.unparse(tree)
        except Exception as e:
            logger.error(f"AST Mutation failed for {expression}: {e}")
            return expression

    @staticmethod
    def crossover(expr1: str, expr2: str) -> str:
        """Performs compiler-grade AST Crossover by grafting mathematical sub-trees."""
        try:
            tree1 = ast.parse(expr1, mode='eval')
            tree2 = ast.parse(expr2, mode='eval')
            
            # Extract viable subtrees (Function calls / mathematical blocks)
            nodes1 = [n for n in ast.walk(tree1) if isinstance(n, ast.Call)]
            nodes2 = [n for n in ast.walk(tree2) if isinstance(n, ast.Call)]
            
            if not nodes1 or not nodes2:
                return expr1 # Fallback to elitism behavior
                
            target_node = random.choice(nodes1)
            replacement_node = copy.deepcopy(random.choice(nodes2))
            
            class CrossoverTransformer(ast.NodeTransformer):
                def __init__(self, target, replacement):
                    self.target = target
                    self.replacement = replacement
                    self.replaced = False
                    
                def generic_visit(self, node):
                    if node is self.target and not self.replaced:
                        self.replaced = True
                        return self.replacement
                    return super().generic_visit(node)
            
            new_tree = CrossoverTransformer(target_node, replacement_node).visit(tree1)
            ast.fix_missing_locations(new_tree)
            child_expr = ast.unparse(new_tree)
            
            # Re-wrap in group_neutralize if the root node was swapped out and lost it
            if "group_neutralize" not in child_expr:
                return f"group_neutralize({child_expr}, {config.DEFAULT_NEUTRALIZATION})"
            return child_expr
            
        except Exception as e:
            logger.error(f"AST Crossover failed between {expr1} and {expr2}: {e}")
            return expr1


class AlphaOrchestrator:
    def __init__(self):
        self.network = NetworkEngine()
        self.llm_generator = LLMSeedGenerator()
        self.population: List[Dict] = []
        self.executor = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_SIMULATIONS)
        self.submission_count = 0
        
        # Upgrade #2: Spatial Memory (Vector Database)
        self.history_exprs = []
        self.history_scores = []
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))

    async def _simulate_alpha(self, expression: str) -> tuple[float, float, str]:
        """Asynchronously simulates an alpha and returns its fitness, turnover, and alpha_id."""
        
        # 2. Spatial Memory Check
        if len(self.history_exprs) > 5:
            try:
                vecs = self.vectorizer.fit_transform(self.history_exprs + [expression])
                sims = cosine_similarity(vecs[-1:], vecs[:-1])[0]
                max_sim = sims.max()
                if max_sim > 0.90:
                    idx = sims.argmax()
                    prev_score = self.history_scores[idx]
                    if prev_score < 1.0:
                        logger.info(f"Spatial Memory: Skipping {expression} (Sim: {max_sim:.2f} to bad alpha)")
                        return prev_score, 1.0, ""
            except Exception as e:
                logger.warning(f"Spatial memory check failed: {e}")

        logger.info(f"Submitting alpha for simulation: {expression}")
        payload = {
            "type": "REGULAR",
            "settings": {
                "instrumentType": config.DEFAULT_INSTRUMENT,
                "region": "USA",
                "universe": "TOP3000",
                "delay": config.DEFAULT_DELAY,
                "decay": config.DEFAULT_DECAY,
                "neutralization": config.DEFAULT_NEUTRALIZATION,
                "truncation": config.DEFAULT_TRUNCATION,
                "pasteurization": "ON",
                "unitHandling": "VERIFY",
                "nanHandling": "ON",
                "language": "FASTEXPR",
                "visualization": False
            },
            "regular": expression
        }
        
        try:
            # Submit to live WorldQuant API
            response_data = await self.network.request("POST", "/simulations", json=payload)
            
            self.submission_count += 1
            logger.info(f"Alpha successfully transmitted! (Total Session Submissions: {self.submission_count})")
                
            # The API usually returns a URL to poll for results. We need to poll it.
            # Assuming the network_engine handles polling or we do it here. 
            # For this integration, we'll assume the API returns the simulation location
            if "Location" in response_data or "url" in response_data:
                poll_url = response_data.get("Location") or response_data.get("url")
                
                # Basic polling loop
                for _ in range(60): # Max 60 attempts (~1-2 minutes)
                    await asyncio.sleep(2)
                    result_data = await self.network.request("GET", poll_url.replace(config.WQ_BASE_URL, ""))
                    
                    status = result_data.get("status")
                    if status == "ERROR":
                        logger.error(f"WorldQuant API Error for {expression}: {result_data}")
                        return -1.0, 1.0, "" # returns sharpe, turnover, alpha_id
                    elif status == "COMPLETE":
                        try:
                            # Attempting common WQ Brain JSON structure
                            is_data = result_data.get("is", {})
                            fitness = float(is_data.get("sharpe", -1.0))
                            turnover = float(is_data.get("turnover", 1.0))
                            
                            # Extract Alpha ID from payload for correlation defense
                            alpha_id = result_data.get("alpha", str(result_data.get("id", "")))
                            if isinstance(alpha_id, dict):
                                alpha_id = alpha_id.get("id", "")
                                
                            logger.info(f"Live Alpha {expression} completed with Sharpe: {fitness:.2f} | Turnover: {turnover:.2%}")
                            return fitness, turnover, alpha_id
                        except Exception as parse_e:
                            logger.error(f"Failed to parse metrics from completed simulation: {parse_e}")
                            return -1.0, 1.0, ""
                            
            logger.error(f"Simulation submission failed, no polling location returned: {response_data}")
            return -1.0, 1.0, ""
            
        except Exception as e:
            logger.error(f"Simulation failed for {expression}: {e}")
            return -1.0, 1.0, ""

    async def _evaluate_population(self, expressions: List[str]):
        """Evaluates a batch of alphas concurrently."""
        tasks = []
        valid_expressions = []
        for expr in expressions:
            is_valid, corrected_expr = SyntaxValidator.parse_and_validate(expr)
            
            # 3. Pre-Flight Statistical Pruning
            if is_valid and SyntaxValidator.is_tautology(corrected_expr):
                logger.info(f"Pruner: Discarded tautological expression: {corrected_expr}")
                is_valid = False

            if is_valid:
                # Neutralize expressions to prevent correlated portfolio risks
                if "group_neutralize" not in corrected_expr:
                    final_expr = f"group_neutralize({corrected_expr}, {config.DEFAULT_NEUTRALIZATION})"
                else:
                    final_expr = corrected_expr
                valid_expressions.append(final_expr)
                tasks.append(self._simulate_alpha(final_expr))
            else:
                valid_expressions.append(expr)
                tasks.append(asyncio.sleep(0, result=(-1.0, 1.0, "")))
                
        results = await asyncio.gather(*tasks)
        
        # Log to winners.csv
        with open("winners.csv", "a") as f:
            for expr, (score, turnover, alpha_id) in zip(valid_expressions, results):
                if score >= -1.0: # Valid simulation result
                    self.history_exprs.append(expr)
                    self.history_scores.append(score)
                    self.population.append({"expression": expr, "fitness": score, "turnover": turnover})
                    
                    # Advanced Multi-Objective Filtering: High Sharpe + Low Turnover
                    if score > 1.25 and turnover < 0.70:
                        
                        # 4. Auto-Correlation Defense
                        is_correlated = False
                        if alpha_id:
                            try:
                                logger.info(f"Checking Auto-Correlation for strong alpha {alpha_id}...")
                                corr_res = await self.network.request("GET", f"/alphas/{alpha_id}/correlations/self")
                                
                                correlations = []
                                if isinstance(corr_res, list):
                                    correlations = [c.get("value", c.get("correlation", 0)) for c in corr_res]
                                elif isinstance(corr_res, dict) and "results" in corr_res:
                                    correlations = [c.get("value", c.get("correlation", 0)) for c in corr_res["results"]]
                                
                                max_corr = max([float(c) for c in correlations if c]) if correlations else 0
                                if max_corr > 0.70:
                                    logger.warning(f"Auto-Correlation Defense: Discarding {expr}. Max correlation is {max_corr:.2f}")
                                    is_correlated = True
                            except Exception as e:
                                logger.error(f"Correlation check failed for {alpha_id}: {e}")
                                
                        if not is_correlated:
                            f.write(f"{expr},{score},{turnover}\n")
                            logger.info(f"🏆 HIGH QUALITY WINNER FOUND: {expr} (Sharpe: {score:.2f} | Turnover: {turnover:.2%})")

    def _select_parents(self) -> List[str]:
        """Tournament selection for the genetic algorithm."""
        tournament = random.sample(self.population, min(len(self.population), config.TOURNAMENT_SIZE))
        tournament.sort(key=lambda x: x["fitness"], reverse=True)
        return [tournament[0]["expression"], tournament[1]["expression"]]

    async def run_factory_loop(self, generations: int = 5):
        """Main orchestrated loop managing ingestion, generation, validation, and evolution."""
        logger.info("Initializing Alpha Factory...")
        
        # 1. Generation Phase
        logger.info("Generating initial seed population...")
        
        # Request fewer templates since we expand them
        template_count = max(1, config.POPULATION_SIZE // 10)
        templates = self.llm_generator.generate_seed_alphas(template_count)
        
        if not templates:
            logger.warning("No seeds generated from LLM. Injecting advanced Quant Library templates for bootstrap.")
            templates = config.QUANT_TEMPLATES
        
        # Validate Templates by stripping curly braces to mock valid variables
        valid_templates = []
        for template in templates:
            mock_template = template.replace("{", "").replace("}", "")
            is_valid, _ = SyntaxValidator.parse_and_validate(mock_template)
            if is_valid:
                valid_templates.append(template)
            else:
                logger.warning(f"Template failed structural validation: {template}")
                
        if not valid_templates:
            logger.info("Injecting Quant Library templates for robust bootstrapping.")
            valid_templates = config.QUANT_TEMPLATES

        # Expand Templates smartly using typed dictionaries
        expanded_population = []
        for template in valid_templates:
            for _ in range(3): # Create 3 variants per template
                expr = template
                
                # Typed Placeholder Replacements
                if "{PRICE}" in expr:
                    expr = expr.replace("{PRICE}", random.choice(config.PRICE_FIELDS))
                if "{FUNDAMENTAL}" in expr:
                    expr = expr.replace("{FUNDAMENTAL}", random.choice(config.FUNDAMENTAL_FIELDS))
                if "{MOMENTUM}" in expr:
                    expr = expr.replace("{MOMENTUM}", random.choice(config.MOMENTUM_FIELDS))
                    
                # Generic Field Replacement (if {FIELD} is still used by LLM)
                while "{FIELD}" in expr:
                    expr = expr.replace("{FIELD}", random.choice(config.DATA_DICTIONARY), 1)
                    
                # Numeric Parameter Replacements
                expr = expr.replace("{LOOKBACK_SHORT}", str(random.choice([5, 10, 20])))
                expr = expr.replace("{LOOKBACK_LONG}", str(random.choice([60, 120, 250])))
                expr = expr.replace("{NEUTRALIZATION}", config.DEFAULT_NEUTRALIZATION)
                
                expanded_population.append(expr)
                
        expanded_population = expanded_population[:config.POPULATION_SIZE]

        # 2. Initial Evaluation
        await self._evaluate_population(expanded_population)
        
        # 3. Evolution Loop
        for gen in range(generations):
            logger.info(f"--- Starting Generation {gen+1} ---")
            self.population.sort(key=lambda x: x["fitness"], reverse=True)
            
            new_generation = []
            
            # Elitism: carry over the top performers
            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
            new_generation.extend([p["expression"] for p in self.population[:elite_count]])
            
            # Crossover and Mutation
            while len(new_generation) < config.POPULATION_SIZE:
                parents = self._select_parents()
                offspring = GeneticEngine.crossover(parents[0], parents[1])
                offspring = GeneticEngine.mutate(offspring)
                new_generation.append(offspring)
            
            # Reset population and evaluate new generation
            self.population = []
            await self._evaluate_population(new_generation)

        logger.info("Alpha Factory execution completed.")

    async def shutdown(self):
        await self.network.close()

if __name__ == "__main__":
    orchestrator = AlphaOrchestrator()
    try:
        asyncio.run(orchestrator.run_factory_loop(generations=2))
    finally:
        asyncio.run(orchestrator.shutdown())

```

## File: `probe_wq.py`
```python
import asyncio
import json
from network_engine import NetworkEngine
import config

async def probe():
    net = NetworkEngine()
    
    endpoints = [
        "/data-fields?instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000&limit=50",
        "/operators",
        "/simulations"
    ]
    
    for ep in endpoints:
        print(f"Probing {ep} ...")
        try:
            res = await net.request("GET", ep)
            print(f"SUCCESS {ep}")
            if "data-fields" in ep:
                fields = [f["id"] for f in res.get("results", [])]
                print(f"Sample fields: {fields[:10]}")
                with open("fields.json", "w") as f:
                    json.dump(fields, f)
            elif "operators" in ep:
                # Assuming operators return list or dict with results
                ops = [o["name"] if "name" in o else o["id"] for o in res] if isinstance(res, list) else res
                print(f"Sample operators: {str(ops)[:100]}")
                with open("operators.json", "w") as f:
                    json.dump(res, f)
        except Exception as e:
            print(f"FAILED {ep}: {e}")
            
    await net.close()

if __name__ == "__main__":
    asyncio.run(probe())
```

## File: `PROJECT_CONTEXT.md`
```markdown
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
```

## File: `AGENT_INSTRUCTIONS.md`
```markdown
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
```

