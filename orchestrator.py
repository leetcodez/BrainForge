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
