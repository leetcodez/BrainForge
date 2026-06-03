import asyncio
import logging
import random
import ast
import copy
import os
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from network_engine import NetworkEngine
from syntax_validator import SyntaxValidator
from llm_seed_generator import LLMSeedGenerator
from db_manager import init_db, save_alpha
from hyper_tuner import AlphaTuner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class GeneticEngine:
    """Handles the Seed-and-Mutate framework using Compiler-Grade AST manipulations & Bloat Control."""
    
    @staticmethod
    def ast_depth(node):
        """Calculates the absolute depth of an AST. Used for Parsimony Pressure."""
        if not isinstance(node, ast.AST):
            return 0
        return 1 + max((GeneticEngine.ast_depth(child) for child in ast.iter_child_nodes(node)), default=0)

    @staticmethod
    def hoist_mutation(expression: str) -> str:
        """Actively shrinks tree bloat by hoisting a nested sub-tree to replace its parent."""
        try:
            tree = ast.parse(expression, mode='eval')
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
            if len(calls) < 2:
                return expression # Too shallow to hoist
            
            # Select a random function call node
            parent = random.choice(calls)
            # Find its children that are also function calls
            child_calls = [n for n in parent.args if isinstance(n, ast.Call)]
            if child_calls:
                hoisted = random.choice(child_calls)
                # We return the hoisted sub-tree as the new root (in a full AST walk we would patch the parent, 
                # but returning the sub-tree directly acts as a massive pruning mechanism).
                return ast.unparse(hoisted)
            return expression
        except Exception:
            return expression

    @staticmethod
    def mutate(expression: str) -> str:
        """Applies stochastic genetic mutation on AST nodes guaranteeing syntax validity."""
        if random.random() > config.MUTATION_RATE:
            return expression
            
        # 1. Hoist Mutation Trigger (Bloat Control)
        if random.random() < 0.20:
            return GeneticEngine.hoist_mutation(expression)
            
        try:
            tree = ast.parse(expression, mode='eval')
            nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Constant, ast.Call))]
            
            if not nodes:
                return expression
                
            node = random.choice(nodes)
            
            # 2. Grammar-Guided Semantic Type Validation during Point Mutation
            if isinstance(node, ast.Name):
                if node.id in config.PRICE_FIELDS:
                    node.id = random.choice(config.PRICE_FIELDS)
                elif node.id in config.FUNDAMENTAL_FIELDS:
                    node.id = random.choice(config.FUNDAMENTAL_FIELDS)
                elif node.id in config.MOMENTUM_FIELDS:
                    node.id = random.choice(config.MOMENTUM_FIELDS)
            elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                node.value = random.choice([5, 10, 20, 60, 120, 250])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
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
            
            nodes1 = [n for n in ast.walk(tree1) if isinstance(n, ast.Call)]
            nodes2 = [n for n in ast.walk(tree2) if isinstance(n, ast.Call)]
            
            if not nodes1 or not nodes2:
                return expr1
                
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
        init_db()
        
        # Spatial Memory
        self.history_exprs = []
        self.history_scores = []
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        
        # Experience Memory (Ralph Loop)
        self.experience_memory = []

    async def _simulate_alpha(self, expression: str) -> tuple[float, float, str]:
        """Asynchronously simulates an alpha and returns its fitness, turnover, and alpha_id."""
        if len(self.history_exprs) > 5:
            try:
                vecs = self.vectorizer.fit_transform(self.history_exprs + [expression])
                sims = cosine_similarity(vecs[-1:], vecs[:-1])[0]
                max_sim = sims.max()
                if max_sim > 0.98:
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
            response_data = await self.network.request("POST", "/simulations", json=payload)
            self.submission_count += 1
            logger.info(f"Alpha successfully transmitted! (Total Session Submissions: {self.submission_count})")
                
            if "Location" in response_data or "url" in response_data:
                poll_url = response_data.get("Location") or response_data.get("url")
                for _ in range(60):
                    await asyncio.sleep(2)
                    result_data = await self.network.request("GET", poll_url.replace(config.WQ_BASE_URL, ""))
                    status = result_data.get("status")
                    if status == "ERROR":
                        logger.error(f"WorldQuant API Error for {expression}: {result_data}")
                        return -1.0, 1.0, ""
                    elif status == "COMPLETE":
                        try:
                            is_data = result_data.get("is", {})
                            fitness = float(is_data.get("sharpe", -1.0))
                            turnover = float(is_data.get("turnover", 1.0))
                            alpha_id = result_data.get("alpha", str(result_data.get("id", "")))
                            if isinstance(alpha_id, dict):
                                alpha_id = alpha_id.get("id", "")
                            logger.info(f"Live Alpha {expression} completed with Sharpe: {fitness:.2f} | Turnover: {turnover:.2%}")
                            return fitness, turnover, alpha_id
                        except Exception as parse_e:
                            logger.error(f"Failed to parse metrics: {parse_e}")
                            return -1.0, 1.0, ""
            return -1.0, 1.0, ""
        except Exception as e:
            logger.error(f"Simulation failed for {expression}: {e}")
            return -1.0, 1.0, ""

    def _nsga_ii_sort(self, population: List[Dict]) -> List[Dict]:
        """Multi-Objective Optimization using Non-dominated Sorting and Crowding Distance."""
        fronts = [[]]
        for p in population:
            p['S'] = []
            p['n'] = 0
            for q in population:
                # Objectives: Maximize adjusted_fitness, Minimize turnover
                better_in_all = (p['adjusted_fitness'] >= q['adjusted_fitness']) and (p['turnover'] <= q['turnover'])
                strictly_better_in_one = (p['adjusted_fitness'] > q['adjusted_fitness']) or (p['turnover'] < q['turnover'])
                
                if better_in_all and strictly_better_in_one:
                    p['S'].append(q)
                else:
                    q_better_in_all = (q['adjusted_fitness'] >= p['adjusted_fitness']) and (q['turnover'] <= p['turnover'])
                    q_strictly_better = (q['adjusted_fitness'] > p['adjusted_fitness']) or (q['turnover'] < p['turnover'])
                    if q_better_in_all and q_strictly_better:
                        p['n'] += 1
            if p['n'] == 0:
                p['rank'] = 0
                fronts[0].append(p)
        
        i = 0
        while fronts[i]:
            next_front = []
            for p in fronts[i]:
                for q in p['S']:
                    q['n'] -= 1
                    if q['n'] == 0:
                        q['rank'] = i + 1
                        next_front.append(q)
            i += 1
            fronts.append(next_front)
        
        fronts = fronts[:-1]
        
        # Calculate Crowding Distance
        for front in fronts:
            l = len(front)
            if l == 0: continue
            for p in front: p['distance'] = 0.0
            
            # Distance by Adjusted Fitness
            front.sort(key=lambda x: x['adjusted_fitness'])
            front[0]['distance'] = float('inf')
            front[-1]['distance'] = float('inf')
            f_min, f_max = front[0]['adjusted_fitness'], front[-1]['adjusted_fitness']
            if f_max != f_min:
                for j in range(1, l - 1):
                    front[j]['distance'] += (front[j+1]['adjusted_fitness'] - front[j-1]['adjusted_fitness']) / (f_max - f_min)
                    
            # Distance by Turnover
            front.sort(key=lambda x: x['turnover'])
            front[0]['distance'] = float('inf')
            front[-1]['distance'] = float('inf')
            t_min, t_max = front[0]['turnover'], front[-1]['turnover']
            if t_max != t_min:
                for j in range(1, l - 1):
                    front[j]['distance'] += abs(front[j+1]['turnover'] - front[j-1]['turnover']) / (t_max - t_min)
        
        flattened = []
        for front in fronts:
            # Sort front by crowding distance (descending) to preserve diversity
            front.sort(key=lambda x: (-x['distance']))
            flattened.extend(front)
            
        return flattened

    async def _check_correlation(self, expression: str, alpha_id: str) -> bool:
        """Checks if the alpha is too correlated with the existing portfolio."""
        if not alpha_id:
            return False
            
        try:
            corr_res = await self.network.request("GET", f"/alphas/{alpha_id}/correlations/self")
            correlations = []
            if isinstance(corr_res, list):
                correlations = [c.get("value", c.get("correlation", 0)) for c in corr_res]
            elif isinstance(corr_res, dict) and "results" in corr_res:
                correlations = [c.get("value", c.get("correlation", 0)) for c in corr_res["results"]]
            
            max_corr = max([float(c) for c in correlations if c]) if correlations else 0
            if max_corr > 0.70:
                logger.warning(f"Auto-Correlation Defense: Discarding {expression}. Max correlation is {max_corr:.2f}")
                
                # Feedback loop for correlation
                thought = f"Expression '{expression}' achieved high Sharpe but is highly correlated (>0.70) to existing models. Search space is saturated here."
                self.experience_memory.append(thought)
                return True
        except Exception as e:
            logger.error(f"Correlation check failed for {alpha_id}: {e}")
        return False

    async def _evaluate_population(self, expressions: List[str]):
        """Evaluates a batch of alphas concurrently and manages Closed-Loop Learning."""
        tasks = []
        valid_expressions = []
        for expr in expressions:
            is_valid, corrected_expr = SyntaxValidator.parse_and_validate(expr)
            
            if is_valid and SyntaxValidator.is_tautology(corrected_expr):
                logger.info(f"Pruner: Discarded tautological expression: {corrected_expr}")
                is_valid = False

            if is_valid:
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
        
        for expr, (score, turnover, alpha_id) in zip(valid_expressions, results):
            if score >= -1.0:
                self.history_exprs.append(expr)
                self.history_scores.append(score)
                
                # 1. Parsimony Pressure Execution
                try:
                    ast_tree = ast.parse(expr, mode='eval')
                    depth = GeneticEngine.ast_depth(ast_tree)
                except:
                    depth = 5
                
                adjusted_fitness = score - (config.PARSIMONY_COEFFICIENT * depth)
                
                self.population.append({
                    "expression": expr, 
                    "fitness": score, 
                    "turnover": turnover,
                    "adjusted_fitness": adjusted_fitness
                })
                
                # Save to DB
                save_alpha(expr, alpha_id, 0, score, turnover, adjusted_fitness, depth)
                
                # 2. Thoughts Decompiler (Agentic Feedback Generation)
                if score < 0.20:
                    thought = f"Expression '{expr}' failed (Sharpe {score:.2f}). The operators or fundamental datasets used lack robust predictive edge."
                    self.experience_memory.append(thought)
                elif turnover >= 0.80:
                    thought = f"Expression '{expr}' failed due to massive turnover ({turnover:.2%}). Utilize smoothing operators like ts_decay_linear to reduce transactional friction."
                    self.experience_memory.append(thought)
                
                if 1.0 < score < 1.25 and turnover < 0.60:
                    generalized_expr = expr.replace("10", "{d1}").replace("20", "{d2}")
                    tuner = AlphaTuner(generalized_expr, self._simulate_alpha)
                    optimal_expr, optimized_sharpe, _, tuned_alpha_id = tuner.run_tuning(n_trials=10)
                    save_alpha(optimal_expr, tuned_alpha_id, 0, optimized_sharpe, turnover, adjusted_fitness, depth, is_tuned=1)
                    
                    if optimized_sharpe > 1.25 and turnover < 0.70:
                        is_correlated = await self._check_correlation(optimal_expr, tuned_alpha_id)
                        if not is_correlated:
                            logger.info(f"🏆 HIGH QUALITY TUNED WINNER FOUND: {optimal_expr} (Sharpe: {optimized_sharpe:.2f} | Turnover: {turnover:.2%})")
                
                elif score > 1.25 and turnover < 0.70:
                    is_correlated = await self._check_correlation(expr, alpha_id)
                    if not is_correlated:
                        logger.info(f"🏆 HIGH QUALITY BASE WINNER FOUND: {expr} (Sharpe: {score:.2f} | Turnover: {turnover:.2%})")

    def _select_parents(self) -> List[str]:
        """Parent selection utilizes NSGA-II to capture Pareto-optimal diversity."""
        # Get top tournament_size individuals from the NSGA-II sorted population
        tournament = self.population[:config.TOURNAMENT_SIZE]
        # In an elitist MOEA, the population is already sorted by Pareto Front and Crowding Distance
        # So we just pull the top 2 from the elite selection
        if len(tournament) < 2:
            return [t["expression"] for t in tournament] * 2 if tournament else ["", ""]
        return [tournament[0]["expression"], tournament[1]["expression"]]

    async def run_factory_loop(self, generations: int = 5):
        logger.info("Initializing Gen-2 Alpha Factory with NSGA-II & Parsimony Controls...")
        
        template_count = max(1, config.POPULATION_SIZE // 10)
        # Pass the Experience Memory to the LLM
        templates = self.llm_generator.generate_seed_alphas(template_count, experience_memory=self.experience_memory)
        
        valid_templates = []
        for template in templates:
            mock_template = template.replace("{", "").replace("}", "")
            is_valid, _ = SyntaxValidator.parse_and_validate(mock_template)
            if is_valid:
                valid_templates.append(template)
                
        if not valid_templates:
            logger.info("Injecting Quant Library templates for robust bootstrapping.")
            valid_templates = config.QUANT_TEMPLATES

        expanded_population = []
        for template in valid_templates:
            for _ in range(3):
                expr = template
                
                # Handle bracketed AND unbracketed variants generated by LLM
                for placeholder, field_list in [
                    ("{PRICE}", config.PRICE_FIELDS), ("PRICE", config.PRICE_FIELDS),
                    ("{FUNDAMENTAL}", config.FUNDAMENTAL_FIELDS), ("FUNDAMENTAL", config.FUNDAMENTAL_FIELDS),
                    ("{MOMENTUM}", config.MOMENTUM_FIELDS), ("MOMENTUM", config.MOMENTUM_FIELDS),
                    ("{VOLATILITY}", config.VOLATILITY_FIELDS), ("VOLATILITY", config.VOLATILITY_FIELDS),
                    ("{MACRO}", config.MACRO_FIELDS), ("MACRO", config.MACRO_FIELDS),
                    ("{SIZE}", config.SIZE_FIELDS), ("SIZE", config.SIZE_FIELDS),
                    ("{FIELD}", config.DATA_DICTIONARY), ("FIELD", config.DATA_DICTIONARY)
                ]:
                    while placeholder in expr:
                        expr = expr.replace(placeholder, random.choice(field_list), 1)
                
                expr = expr.replace("{LOOKBACK_SHORT}", str(random.choice([5, 10, 20])))
                expr = expr.replace("{LOOKBACK_LONG}", str(random.choice([60, 120, 250])))
                expr = expr.replace("LOOKBACK_SHORT", str(random.choice([5, 10, 20])))
                expr = expr.replace("LOOKBACK_LONG", str(random.choice([60, 120, 250])))
                expr = expr.replace("{NEUTRALIZATION}", config.DEFAULT_NEUTRALIZATION)
                expr = expr.replace("NEUTRALIZATION", config.DEFAULT_NEUTRALIZATION)
                
                expanded_population.append(expr)
                
        expanded_population = expanded_population[:config.POPULATION_SIZE]

        await self._evaluate_population(expanded_population)
        
        for gen in range(generations):
            logger.info(f"--- Starting Generation {gen+1} (NSGA-II Frontier) ---")
            
            # Sort the entire population using Pareto Dominance
            self.population = self._nsga_ii_sort(self.population)
            
            new_generation = []
            
            # Elitism: carry over the top Pareto Front performers
            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
            new_generation.extend([p["expression"] for p in self.population[:elite_count]])
            
            while len(new_generation) < config.POPULATION_SIZE:
                parents = self._select_parents()
                if not parents[0]: break
                offspring = GeneticEngine.crossover(parents[0], parents[1])
                offspring = GeneticEngine.mutate(offspring)
                new_generation.append(offspring)
            
            # We don't wipe the population in NSGA-II, we merge and sort the N+N population to preserve elites,
            # but to save API limits and memory in this specific pipeline, we keep the population rolling and growing
            # and just select the top N after the next evaluation loop.
            # To prevent extreme RAM growth, we cap the standing population before evaluating the new one.
            self.population = self.population[:config.POPULATION_SIZE]
            await self._evaluate_population(new_generation)

        logger.info("Alpha Factory execution completed.")

    async def shutdown(self):
        await self.network.close()

if __name__ == "__main__":
    orchestrator = AlphaOrchestrator()
    try:
        asyncio.run(orchestrator.run_factory_loop(generations=config.GENERATIONS))
    finally:
        asyncio.run(orchestrator.shutdown())