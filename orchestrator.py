import asyncio
import logging
import random
import ast
import copy
import queue
import threading
from typing import List, Dict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from network_engine import NetworkEngine
from syntax_validator import SyntaxValidator
from llm_seed_generator import LLMSeedGenerator
from db_manager import DatabaseManager
from oos_deflation import OOSDeflationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class GeneticEngine:
    @staticmethod
    def ast_depth(node):
        if not isinstance(node, ast.AST):
            return 0
        return 1 + max((GeneticEngine.ast_depth(child) for child in ast.iter_child_nodes(node)), default=0)

    @staticmethod
    def _field_group_for(field_name: str):
        for field_group in config.FIELD_GROUPS.values():
            if field_name in field_group:
                return field_group
        return None

    @staticmethod
    def _compatible_operator_choices(operator_name: str, arg_count: int) -> List[str]:
        category = config.OPERATOR_CATEGORIES.get(operator_name)
        if not category:
            return []
        return [
            candidate
            for candidate in config.OPERATORS_BY_CATEGORY.get(category, [])
            if SyntaxValidator.operator_accepts_arity(candidate, arg_count)
        ]

    @staticmethod
    def _call_signature(node: ast.Call):
        if not isinstance(node.func, ast.Name):
            return None
        func_name = node.func.id.lower()
        return config.OPERATOR_CATEGORIES.get(func_name), len(node.args) + len(node.keywords)

    @staticmethod
    def _calls_compatible(target: ast.Call, replacement: ast.Call) -> bool:
        target_sig = GeneticEngine._call_signature(target)
        replacement_sig = GeneticEngine._call_signature(replacement)
        if not target_sig or not replacement_sig:
            return False
        target_category, target_arity = target_sig
        replacement_category, replacement_arity = replacement_sig
        return target_category == replacement_category and target_arity == replacement_arity

    @staticmethod
    def _ensure_neutralized(expression: str) -> str:
        if "group_neutralize" in expression:
            return expression
        return f"group_neutralize({expression}, {random.choice(config.NEUTRALIZATIONS)})"

    @staticmethod
    def hoist_mutation(expression: str) -> str:
        try:
            tree = ast.parse(expression, mode='eval')
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
            if len(calls) < 2:
                return expression

            parent = random.choice(calls)
            child_calls = [n for n in parent.args if isinstance(n, ast.Call)]
            if child_calls:
                hoisted = random.choice(child_calls)
                return ast.unparse(hoisted)
            return expression
        except Exception:
            return expression

    @staticmethod
    def mutate(expression: str) -> str:
        if random.random() > config.MUTATION_RATE:
            return expression

        if random.random() < 0.20:
            return GeneticEngine.hoist_mutation(expression)

        try:
            tree = ast.parse(expression, mode='eval')
            nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Constant, ast.Call))]

            if not nodes:
                return expression

            node = random.choice(nodes)

            if isinstance(node, ast.Name):
                field_group = GeneticEngine._field_group_for(node.id)
                if field_group:
                    node.id = random.choice(field_group)
            elif isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value >= 2:
                node.value = random.choice([5, 10, 20, 40, 60, 120, 250])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                arg_count = len(node.args) + len(node.keywords)
                choices = GeneticEngine._compatible_operator_choices(node.func.id.lower(), arg_count)
                if choices:
                    node.func.id = random.choice(choices)

            ast.fix_missing_locations(tree)
            mutated_expr = ast.unparse(tree)
            is_valid, corrected_expr = SyntaxValidator.parse_and_validate(mutated_expr)
            return corrected_expr if is_valid else expression
        except Exception as e:
            logger.error(f"Mutation error: {e}")
            return expression

    @staticmethod
    def crossover(expr1: str, expr2: str) -> str:
        try:
            tree1 = ast.parse(expr1, mode='eval')
            tree2 = ast.parse(expr2, mode='eval')

            nodes1 = [n for n in ast.walk(tree1) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            nodes2 = [n for n in ast.walk(tree2) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]

            if not nodes1 or not nodes2:
                return expr1

            target_node = random.choice(nodes1)
            compatible_replacements = [node for node in nodes2 if GeneticEngine._calls_compatible(target_node, node)]
            if not compatible_replacements:
                return expr1
            replacement_node = copy.deepcopy(random.choice(compatible_replacements))

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
            child_expr = GeneticEngine._ensure_neutralized(ast.unparse(new_tree))
            is_valid, corrected_expr = SyntaxValidator.parse_and_validate(child_expr)
            if not is_valid or SyntaxValidator.is_tautology(corrected_expr):
                return expr1
            return corrected_expr
        except Exception as e:
            logger.error(f"Crossover error: {e}")
            return expr1


class AlphaOrchestrator:
    def __init__(self):
        self.network = NetworkEngine()
        self.llm_generator = LLMSeedGenerator()
        self.deflation_engine = OOSDeflationEngine()
        self.db = DatabaseManager()
        self.population: List[Dict] = []
        self.submission_count = 0

        self.history_exprs = []
        self.history_scores = []
        self.history_scores_by_canonical = {}
        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))

        self.sim_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SIMULATIONS)
        self.experience_memory = []
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await self.db.init_db()
        try:
            rows = await self.db.load_history()
            for expression, universe, decay, sharpe in rows:
                try:
                    canonical = SyntaxValidator.canonicalize(expression)
                except Exception:
                    canonical = expression
                
                cache_key = f"{canonical}|{universe}|{decay}"
                self.history_exprs.append(expression)
                self.history_scores.append(sharpe)
                self.history_scores_by_canonical[cache_key] = sharpe
            logger.info(f"Loaded {len(self.history_exprs)} historical formulas.")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
        self._initialized = True

    @staticmethod
    def _series_length(value) -> int | None:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for nested_key in ("values", "returns", "data", "series"):
                nested_value = value.get(nested_key)
                nested_length = AlphaOrchestrator._series_length(nested_value)
                if nested_length:
                    return nested_length
        return None

    @staticmethod
    def _extract_track_record_length(result_data: Dict, is_data: Dict) -> int:
        for payload in (is_data, result_data):
            for key in ("trackRecordLength", "track_record_length", "sampleSize", "sample_size", "days"):
                value = payload.get(key)
                if isinstance(value, (int, float)) and value > 1:
                    return int(value)

            for key in ("returns", "dailyReturns", "daily_returns", "pnl", "pnlData", "pnl_data"):
                series_length = AlphaOrchestrator._series_length(payload.get(key))
                if series_length and series_length > 1:
                    return series_length

        return config.DEFAULT_TRACK_RECORD_LENGTH

    async def _simulate_alpha(
        self, expression: str, universe: str, decay: int
    ) -> tuple[float, float, str, float, float, int]:
        _failed = (-1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH)

        try:
            canonical = SyntaxValidator.canonicalize(expression)
        except Exception:
            canonical = expression

        cache_key = f"{canonical}|{universe}|{decay}"
        prev = self.history_scores_by_canonical.get(cache_key)
        if prev is not None and prev < 1.0:
            logger.info(f"Skip duplicate: {expression} ({universe}, {decay})")
            return prev, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH

        async with self.sim_semaphore:
            # TF-IDF near-duplicate check
            if len(self.history_exprs) > 5:
                try:
                    loop = asyncio.get_running_loop()
                    def _compute_sim():
                        local_vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
                        recent_history = self.history_exprs[-2000:]
                        recent_scores = self.history_scores[-2000:]
                        vecs = local_vectorizer.fit_transform(recent_history + [expression])
                        sims = cosine_similarity(vecs[-1:], vecs[:-1])[0]
                        return sims.max(), sims.argmax(), recent_scores

                    max_sim, idx, recent_scores = await loop.run_in_executor(None, _compute_sim)

                    if max_sim >= 1.0:
                        prev_score = recent_scores[idx]
                        if prev_score < 1.0:
                            logger.info(f"Skipping similar: {expression}")
                            return prev_score, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH
                except Exception as e:
                    logger.warning(f"Memory check failed: {e}")

            logger.info(f"Simulating: {expression} | Uni: {universe} | Decay: {decay}")
            payload = {
                "type": "REGULAR",
                "settings": {
                    "instrumentType": config.DEFAULT_INSTRUMENT,
                    "region": "USA",
                    "universe": universe,
                    "delay": config.DEFAULT_DELAY,
                    "decay": decay,
                    "neutralization": "NONE",
                    "truncation": config.DEFAULT_TRUNCATION,
                    "pasteurization": "ON",
                    "unitHandling": "VERIFY",
                    "nanHandling": "ON",
                    "language": "FASTEXPR",
                    "visualization": False,
                },
                "regular": expression,
            }

            try:
                response_data = await self.network.request("POST", "/simulations", json=payload)
                self.submission_count += 1

                if "Location" in response_data or "url" in response_data:
                    poll_url = response_data.get("Location") or response_data.get("url")
                    for _ in range(60):
                        await asyncio.sleep(2)
                        result_data = await self.network.request("GET", poll_url.replace(config.WQ_BASE_URL, ""))
                        status = result_data.get("status")
                        if status == "ERROR":
                            logger.error(f"API Error for {expression}")
                            return -1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH
                        elif status == "COMPLETE":
                            try:
                                is_data = result_data.get("is", {})
                                fitness = float(is_data.get("sharpe", -1.0))
                                turnover = float(is_data.get("turnover", 1.0))
                                skew = float(is_data.get("skew", -0.5))
                                kurtosis = float(is_data.get("kurtosis", 4.0))
                                track_record_length = self._extract_track_record_length(result_data, is_data)
                                alpha_id = result_data.get("alpha", str(result_data.get("id", "")))
                                if isinstance(alpha_id, dict):
                                    alpha_id = alpha_id.get("id", "")
                                
                                self.history_scores_by_canonical[cache_key] = fitness
                                logger.info(f"Sharpe={fitness:.2f} | Turnover={turnover:.2%} | {universe} | Decay: {decay} | {expression}")
                                return fitness, turnover, alpha_id, skew, kurtosis, track_record_length
                            except Exception as parse_e:
                                logger.error(f"Parse error: {parse_e}")
                                return -1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH
                return -1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH
            except Exception as e:
                logger.error(f"Simulation failed: {e}")
                return -1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH

    def _nsga_ii_sort(self, population: List[Dict]) -> List[Dict]:
        fronts = [[]]
        for p in population:
            p['S'] = []
            p['n'] = 0
            for q in population:
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

        for front in fronts:
            l = len(front)
            if l == 0: continue
            for p in front: p['distance'] = 0.0

            front.sort(key=lambda x: x['adjusted_fitness'])
            front[0]['distance'] = float('inf')
            front[-1]['distance'] = float('inf')
            f_min, f_max = front[0]['adjusted_fitness'], front[-1]['adjusted_fitness']
            if f_max != f_min:
                for j in range(1, l - 1):
                    front[j]['distance'] += (front[j+1]['adjusted_fitness'] - front[j-1]['adjusted_fitness']) / (f_max - f_min)

            front.sort(key=lambda x: x['turnover'])
            front[0]['distance'] = float('inf')
            front[-1]['distance'] = float('inf')
            t_min, t_max = front[0]['turnover'], front[-1]['turnover']
            if t_max != t_min:
                for j in range(1, l - 1):
                    front[j]['distance'] += abs(front[j+1]['turnover'] - front[j-1]['turnover']) / (t_max - t_min)

        flattened = []
        for front in fronts:
            front.sort(key=lambda x: (-x['distance']))
            flattened.extend(front)

        return flattened

    async def _check_correlation(self, expression: str, alpha_id: str) -> bool:
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
                logger.warning(f"Discarding correlated: {expression}")
                self.experience_memory.append(f"Expression '{expression}' high correlation.")
                return True
        except Exception as e:
            logger.error(f"Correlation check failed: {e}")
        return False

    async def _evaluate_population(self, candidates: List[Dict]):
        _failed = (-1.0, 1.0, "", 0.0, 3.0, config.DEFAULT_TRACK_RECORD_LENGTH)
        tasks = []
        valid_candidates = []

        for candidate in candidates:
            expr = candidate["expression"]
            is_valid, corrected = SyntaxValidator.parse_and_validate(expr)
            if is_valid and SyntaxValidator.is_tautology(corrected):
                is_valid = False

            if is_valid:
                if "group_neutralize" not in corrected and "group_scale" not in corrected:
                    final = f"group_neutralize({corrected}, {random.choice(config.NEUTRALIZATIONS)})"
                else:
                    final = corrected
                final = SyntaxValidator.canonicalize(final)
                candidate["expression"] = final
                valid_candidates.append(candidate)
                tasks.append(self._simulate_alpha(final, candidate["universe"], candidate["decay"]))
            else:
                valid_candidates.append(candidate)
                tasks.append(asyncio.sleep(0, result=_failed))

        results = await asyncio.gather(*tasks)

        elite_exprs = [
            p["expression"]
            for p in self.population[: max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))]
        ]
        records = []

        for candidate, (score, turnover, alpha_id, skew, kurtosis, trl) in zip(valid_candidates, results):
            if score < -1.0:
                continue
                
            expr = candidate["expression"]
            universe = candidate["universe"]
            decay = candidate["decay"]

            self.history_exprs.append(expr)
            self.history_scores.append(score)

            try:
                depth = GeneticEngine.ast_depth(ast.parse(expr, mode="eval"))
            except Exception:
                depth = 5

            dsr = self.deflation_engine.calculate_dsr(
                sharpe=score,
                skew=skew,
                kurtosis=kurtosis,
                track_record_length=trl,
                num_trials=max(10, self.submission_count),
                var_trials=0.5,
            )
            records.append({
                "expression": expr,
                "universe": universe,
                "decay": decay,
                "score": score,
                "turnover": turnover,
                "alpha_id": alpha_id,
                "depth": depth,
                "dsr_score": dsr,
            })

        loop = asyncio.get_running_loop()
        adjusted = await loop.run_in_executor(
            None,
            self.deflation_engine.calculate_orthogonal_fitness_batch,
            [r["expression"] for r in records],
            elite_exprs,
            [r["dsr_score"] for r in records],
        )

        for record, adj_fitness in zip(records, adjusted):
            expr = record["expression"]
            universe = record["universe"]
            decay = record["decay"]
            score = record["score"]
            turnover = record["turnover"]
            depth = record["depth"]
            alpha_id = record["alpha_id"]
            final_fitness = adj_fitness - config.PARSIMONY_COEFFICIENT * depth

            self.population.append({
                "expression": expr,
                "universe": universe,
                "decay": decay,
                "fitness": score,
                "turnover": turnover,
                "adjusted_fitness": final_fitness,
            })

            await self.db.save_alpha(expr, universe, decay, alpha_id, 0, score, turnover, final_fitness, depth)

            if score < 0.20:
                self.experience_memory.append(f"Expression '{expr}' failed (Sharpe {score:.2f}).")
            elif turnover >= 0.80:
                self.experience_memory.append(f"Expression '{expr}' failed with high turnover.")

            if score > 1.25 and turnover < 0.70:
                if not await self._check_correlation(expr, alpha_id):
                    logger.info(f"★ WINNER: {expr} | Uni: {universe} | Decay: {decay}")

    def _select_parents(self) -> List[Dict]:
        tournament = self.population[: config.TOURNAMENT_SIZE]
        if len(tournament) < 2:
            return [tournament[0], tournament[0]] if tournament else [{}, {}]
        return [tournament[0], tournament[1]]

    @staticmethod
    async def _run_blocking(func, *args):
        return await asyncio.to_thread(func, *args)

    async def _generate_templates(self, count: int) -> List[str]:
        return await self._run_blocking(
            self.llm_generator.generate_seed_alphas,
            count,
            self.experience_memory,
        )

    @staticmethod
    def _valid_templates(templates: List[str]) -> List[str]:
        valid_templates = []
        for template in templates:
            mock_template = template.replace("{", "").replace("}", "")
            is_valid, _ = SyntaxValidator.parse_and_validate(mock_template)
            if is_valid:
                valid_templates.append(template)
        return valid_templates

    @staticmethod
    def _expand_templates(
        templates: List[str],
        variants_per_template: int = 3,
        limit: int | None = None,
    ) -> List[Dict]:
        expanded = []
        placeholder_groups = [
            ("{PRICE}", config.PRICE_FIELDS), ("PRICE", config.PRICE_FIELDS),
            ("{FUNDAMENTAL}", config.FUNDAMENTAL_FIELDS), ("FUNDAMENTAL", config.FUNDAMENTAL_FIELDS),
            ("{MOMENTUM}", config.MOMENTUM_FIELDS), ("MOMENTUM", config.MOMENTUM_FIELDS),
            ("{VOLATILITY}", config.VOLATILITY_FIELDS), ("VOLATILITY", config.VOLATILITY_FIELDS),
            ("{MACRO}", config.MACRO_FIELDS), ("MACRO", config.MACRO_FIELDS),
            ("{SIZE}", config.SIZE_FIELDS), ("SIZE", config.SIZE_FIELDS),
            ("{SENTIMENT}", config.SENTIMENT_FIELDS), ("SENTIMENT", config.SENTIMENT_FIELDS),
            ("{RELATIONSHIP}", config.RELATIONSHIP_FIELDS), ("RELATIONSHIP", config.RELATIONSHIP_FIELDS),
            ("{FIELD}", config.DATA_DICTIONARY), ("FIELD", config.DATA_DICTIONARY),
        ]

        for template in templates:
            for _ in range(variants_per_template):
                expr = template
                for placeholder, field_list in placeholder_groups:
                    while placeholder in expr:
                        expr = expr.replace(placeholder, random.choice(field_list), 1)
                expr = expr.replace("{LOOKBACK_SHORT}", str(random.choice([5, 10, 20])))
                expr = expr.replace("{LOOKBACK_LONG}", str(random.choice([60, 120, 250])))
                expr = expr.replace("LOOKBACK_SHORT", str(random.choice([5, 10, 20])))
                expr = expr.replace("LOOKBACK_LONG", str(random.choice([60, 120, 250])))
                
                neutralization = random.choice(config.NEUTRALIZATIONS)
                expr = expr.replace("{NEUTRALIZATION}", neutralization)
                expr = expr.replace("NEUTRALIZATION", neutralization)
                
                expanded.append({
                    "expression": expr,
                    "universe": random.choice(config.UNIVERSES),
                    "decay": random.choice(config.DECAYS)
                })
                
                if limit and len(expanded) >= limit:
                    return expanded
        return expanded

    async def run_factory_loop(self, generations: int = 5):
        await self.initialize()
        logger.info("=== Gen-4 Alpha Factory initialised ===")

        # Attempt to resume from database!
        try:
            top_alphas = await self.db.get_top_population(limit=config.POPULATION_SIZE)
        except Exception as e:
            logger.warning(f"Could not load previous alphas from DB: {e}")
            top_alphas = []

        if top_alphas:
            logger.info(f"🧬 Resuming genetic lineage from {len(top_alphas)} elite alphas stored in DB.")
            for expr, uni, dec, sharpe, turnover, depth in top_alphas:
                dsr = self.deflation_engine.calculate_dsr(
                    sharpe=sharpe, skew=0.0, kurtosis=3.0, track_record_length=1000, num_trials=10, var_trials=0.5
                )
                adj_fitness = dsr - (config.PARSIMONY_COEFFICIENT * depth)
                self.population.append({
                    "expression": expr,
                    "universe": uni,
                    "decay": dec,
                    "fitness": sharpe,
                    "turnover": turnover,
                    "adjusted_fitness": adj_fitness
                })

        template_count = max(1, config.POPULATION_SIZE // 10)
        templates = await self._generate_templates(template_count)
        valid_templates = self._valid_templates(templates) or config.QUANT_TEMPLATES

        needed_seeds = max(0, config.POPULATION_SIZE - len(self.population))
        if needed_seeds > 0:
            seed_population = self._expand_templates(
                valid_templates, variants_per_template=3, limit=needed_seeds
            )
            await self._evaluate_population(seed_population)

        for gen in range(generations):
            logger.info(f"── Generation {gen + 1}/{generations} ──")
            self.population = self._nsga_ii_sort(self.population)

            if self.population and all(p["fitness"] <= 0 for p in self.population[:10]):
                logger.error("Population collapse detected. All top alphas failing.")

            new_gen: List[Dict] = []
            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
            
            new_gen.extend([
                {
                    "expression": p["expression"],
                    "universe": p.get("universe", "TOP3000"),
                    "decay": p.get("decay", 15)
                } 
                for p in self.population[:elite_count]
            ])

            # Adaptive reseeding on experience interval
            if (
                self.experience_memory
                and config.EXPERIENCE_RESEED_INTERVAL > 0
                and (gen + 1) % config.EXPERIENCE_RESEED_INTERVAL == 0
            ):
                adaptive = self._valid_templates(
                    await self._generate_templates(config.EXPERIENCE_RESEED_COUNT)
                )
                new_gen.extend(
                    self._expand_templates(
                        adaptive,
                        variants_per_template=1,
                        limit=config.EXPERIENCE_RESEED_COUNT,
                    )
                )

            # Fill remaining slots via crossover + mutation
            while len(new_gen) < config.POPULATION_SIZE:
                parents = self._select_parents()
                if not parents[0]:
                    break
                    
                p1_expr = parents[0].get("expression", "")
                p2_expr = parents[1].get("expression", "")
                offspring_expr = GeneticEngine.crossover(p1_expr, p2_expr)
                offspring_expr = GeneticEngine.mutate(offspring_expr)
                
                offspring_uni = random.choice([parents[0].get("universe", "TOP3000"), parents[1].get("universe", "TOP3000")])
                offspring_dec = random.choice([parents[0].get("decay", 15), parents[1].get("decay", 15)])
                
                if random.random() < 0.15: offspring_uni = random.choice(config.UNIVERSES)
                if random.random() < 0.15: offspring_dec = random.choice(config.DECAYS)
                
                new_gen.append({
                    "expression": offspring_expr,
                    "universe": offspring_uni,
                    "decay": offspring_dec
                })

            self.population = self.population[:config.POPULATION_SIZE]
            new_gen = new_gen[:config.POPULATION_SIZE]
            await self._evaluate_population(new_gen)

    async def shutdown(self):
        await self.network.close()
        await self.db.close()

async def main():
    orchestrator = AlphaOrchestrator()
    try:
        await orchestrator.run_factory_loop(generations=config.GENERATIONS)
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
