import ast
import asyncio
import copy
import logging
import math
import random
from dataclasses import dataclass

import numpy as np

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine
from oos_deflation import OOSDeflationEngine
from llm_seed_generator import LLMSeedGenerator
from syntax_validator import SyntaxValidator

logger = logging.getLogger(__name__)

# Expression node types that are valid crossover/mutation targets.
EXPR_NODES = (ast.Call, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Compare)

_SHORT_LOOKBACKS = [5, 10, 15, 20, 22]
_LONG_LOOKBACKS = [60, 120, 180, 252]


def _ast_depth(expression: str) -> int:
    try:
        tree = ast.parse(expression, mode="eval")
    except Exception:
        return 1

    def depth(node):
        children = list(ast.iter_child_nodes(node))
        return 1 + max((depth(c) for c in children), default=0)

    return depth(tree)


def _split_group_neutralize(expression):
    """If the outermost call is group_neutralize(inner, GROUP), return
    (inner_expression_str, group_token_str); otherwise (None, None).

    Used to (a) re-wrap the inner logic during ts mutation instead of wrapping
    the whole neutralized alpha, and (b) vary the neutralization in grid search.
    """
    try:
        node = ast.parse(expression, mode="eval").body
    except Exception:
        return None, None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id.lower() == "group_neutralize" and len(node.args) == 2):
        group = node.args[1]
        if isinstance(group, ast.Name):
            try:
                return ast.unparse(node.args[0]), group.id
            except Exception:
                return None, None
    return None, None


@dataclass
class SimulationResult:
    expression: str
    universe: str
    decay: int
    sharpe: float = -1.0
    turnover: float = 1.0
    alpha_id: str = ""
    skew: float = 0.0
    kurtosis: float = 0.0  # EXCESS kurtosis (normal == 0); see config.KURTOSIS_IS_EXCESS
    track_record_length: int = config.DEFAULT_TRACK_RECORD_LENGTH
    valid: bool = False


class GeneticEngine:
    """AST-level mutation & crossover. Every output is validated; on any failure
    we fall back to a parent expression so the pipeline never sees garbage."""

    def __init__(self):
        self._field_set = set(config.DATA_DICTIONARY)
        self._field_group = {}
        for group, fields in config.FIELD_GROUPS.items():
            for f in fields:
                self._field_group[f] = group
        allowed = set(config.ALLOWED_OPERATORS)
        preferred = ["ts_rank", "ts_zscore", "ts_mean", "ts_delta", "ts_std_dev", "ts_decay_linear", "ts_av_diff"]
        self._ts_wrap_ops = [o for o in preferred if o in allowed and SyntaxValidator.operator_accepts_arity(o, 2)]
        if not self._ts_wrap_ops:
            self._ts_wrap_ops = [o for o in preferred if o in allowed]
        self._mutation_ops = [self._mutate_lookback, self._mutate_field, self._mutate_operator, self._mutate_wrap_ts]

    # --- mutation primitives -------------------------------------------------
    def _mutate_lookback(self, expression):
        tree = ast.parse(expression, mode="eval")
        consts = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
        if not consts:
            return None
        node = random.choice(consts)
        node.value = random.choice(_SHORT_LOOKBACKS + _LONG_LOOKBACKS)
        return ast.unparse(tree)

    def _mutate_field(self, expression):
        tree = ast.parse(expression, mode="eval")
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in self._field_set]
        if not names:
            return None
        node = random.choice(names)
        group = self._field_group.get(node.id)
        pool = config.FIELD_GROUPS[group] if group else config.DATA_DICTIONARY
        node.id = random.choice(pool)
        return ast.unparse(tree)

    def _mutate_operator(self, expression):
        tree = ast.parse(expression, mode="eval")
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        if not calls:
            return None
        node = random.choice(calls)
        name = node.func.id.lower()
        arg_count = len(node.args) + len(node.keywords)
        category = config.OPERATOR_CATEGORIES.get(name)
        alternatives = [o for o in config.OPERATORS_BY_CATEGORY.get(category, [])
                        if o != name and SyntaxValidator.operator_accepts_arity(o, arg_count)]
        if not alternatives:
            return None
        node.func.id = random.choice(alternatives)
        return ast.unparse(tree)

    def _mutate_wrap_ts(self, expression):
        if not self._ts_wrap_ops:
            return None
        op = random.choice(self._ts_wrap_ops)
        window = random.choice(_SHORT_LOOKBACKS + _LONG_LOOKBACKS)
        # Wrap the INNER logic and keep neutralization outermost, rather than
        # producing ts_rank(group_neutralize(...), w) which neutralizes-then-
        # ranks (conceptually backwards).
        inner, group = _split_group_neutralize(expression)
        if inner is not None and group is not None:
            return f"group_neutralize({op}({inner}, {window}), {group})"
        return f"{op}({expression}, {window})"

    def mutate(self, expression):
        for _ in range(4):
            op = random.choice(self._mutation_ops)
            try:
                candidate = op(expression)
            except Exception:
                candidate = None
            if candidate and candidate != expression:
                ok, canonical = SyntaxValidator.parse_and_validate(candidate)
                if ok and not SyntaxValidator.is_tautology(canonical):
                    return canonical
        return expression

    # --- crossover -----------------------------------------------------------
    @staticmethod
    def _expression_slots(tree):
        slots = []
        for parent in ast.walk(tree):
            for field_name, value in ast.iter_fields(parent):
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, EXPR_NODES):
                            slots.append((parent, field_name, i, item))
                elif isinstance(value, EXPR_NODES):
                    slots.append((parent, field_name, None, value))
        return slots

    def crossover(self, expr1, expr2):
        try:
            t1 = ast.parse(expr1, mode="eval")
            t2 = ast.parse(expr2, mode="eval")
        except Exception:
            return expr1
        slots = self._expression_slots(t1)
        donors = [n for n in ast.walk(t2) if isinstance(n, EXPR_NODES)]
        if not slots or not donors:
            return expr1
        parent, field_name, index, _ = random.choice(slots)
        donor = copy.deepcopy(random.choice(donors))
        if index is None:
            setattr(parent, field_name, donor)
        else:
            getattr(parent, field_name)[index] = donor
        ast.fix_missing_locations(t1)
        try:
            candidate = ast.unparse(t1)
        except Exception:
            return expr1
        ok, canonical = SyntaxValidator.parse_and_validate(candidate)
        if ok and not SyntaxValidator.is_tautology(canonical):
            return canonical
        return expr1


class AlphaFactory:
    def __init__(self):
        if config.RANDOM_SEED is not None:
            random.seed(config.RANDOM_SEED)
            np.random.seed(config.RANDOM_SEED)
        self.db = DatabaseManager()
        self.network = NetworkEngine()
        self.deflation = OOSDeflationEngine()
        self.llm = LLMSeedGenerator()
        self.genetic = GeneticEngine()

        self.population = []
        self.result_cache = {}
        self.history_exprs = []
        self.history_scores = []
        self.loser_exprs = []
        self.evaluated_canon = set()
        self.grid_searched = set()
        self.submission_count = 0
        self.generation = 0

        self.sim_semaphore = None
        self._state_lock = asyncio.Lock()
        self._active_tasks = set()

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _safe_float(value, default):
        try:
            f = float(value)
            return f if math.isfinite(f) else default
        except (TypeError, ValueError):
            return default

    def _estimate_var_trials(self) -> float:
        sqrt_periods = math.sqrt(config.PERIODS_IN_YEAR)
        per_period = [s / sqrt_periods for s in self.history_scores if s is not None and math.isfinite(s)]
        if len(per_period) >= 2:
            return float(np.var(per_period))
        return (0.4 / sqrt_periods) ** 2

    # --- lifecycle -----------------------------------------------------------
    async def initialize(self):
        await self.db.init_db()
        self.sim_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SIMULATIONS)
        history = await self.db.load_history()
        for row in history:
            expr, universe, decay, sharpe, turnover, skew, kurtosis, trl, alpha_id = row
            key = f"{expr}|{universe}|{decay}"
            self.evaluated_canon.add(key)
            self.result_cache[key] = SimulationResult(
                expression=expr, universe=universe, decay=decay,
                sharpe=sharpe if sharpe is not None else -1.0,
                turnover=turnover if turnover is not None else 1.0,
                skew=skew or 0.0, kurtosis=kurtosis if kurtosis is not None else 0.0,
                track_record_length=trl or config.DEFAULT_TRACK_RECORD_LENGTH,
                alpha_id=alpha_id or "", valid=sharpe is not None,
            )
            if sharpe is not None:
                self.history_exprs.append(expr)
                self.history_scores.append(sharpe)
                if sharpe < config.MIN_SHARPE:
                    self.loser_exprs.append(expr)
        logger.info(f"Loaded {len(history)} historical alphas from memory.")

    async def shutdown(self):
        for task in list(self._active_tasks):
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
            self._active_tasks.clear()
        await self.network.close()
        await self.db.close()

    # --- simulation ----------------------------------------------------------
    async def _simulate_alpha(self, expression, universe, decay) -> SimulationResult:
        cache_key = f"{expression}|{universe}|{decay}"
        if cache_key in self.result_cache:
            return self.result_cache[cache_key]

        result = SimulationResult(expression=expression, universe=universe, decay=decay)
        payload = config.build_simulation_payload(expression, universe, decay)

        # Hold a concurrency slot ONLY for the submission POST. Polling happens
        # outside the semaphore so a long-running simulation never starves the
        # ability to submit new ones.
        poll_url = None
        async with self.sim_semaphore:
            resp = await self.network.request("POST", "/simulations", json=payload)
            self.submission_count += 1
            if resp["status_code"] not in (200, 201):
                logger.info(f"Simulation rejected (HTTP {resp['status_code']}).")
                self.result_cache[cache_key] = result
                return result
            poll_url = resp.get("location")
            body = resp.get("json")
            if not poll_url and isinstance(body, dict):
                poll_url = body.get("location") or body.get("url")

        if not poll_url:
            logger.warning("Simulation accepted but no poll URL returned.")
            self.result_cache[cache_key] = result
            return result

        poll_endpoint = poll_url.replace(config.WQ_BASE_URL, "")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + config.SIMULATION_POLL_TIMEOUT_SECS
        alpha_id = None
        errored = False
        while loop.time() < deadline:
            await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
            poll = await self.network.request("GET", poll_endpoint)
            pbody = poll.get("json") or {}
            status = str(pbody.get("status", "")).upper()
            if status in ("ERROR", "FAIL", "FAILED"):
                errored = True
                break
            if status == "COMPLETE" or pbody.get("alpha"):
                alpha_id = pbody.get("alpha")
                break

        if not alpha_id:
            # Cache genuine errors so we don't retry a broken expression, but do
            # NOT cache timeouts (those may succeed on a later, calmer run).
            if errored:
                self.result_cache[cache_key] = result
            return result

        detail = await self.network.request("GET", f"/alphas/{alpha_id}")
        metrics = (detail.get("json") or {}).get("is") or {}
        result.alpha_id = alpha_id
        result.sharpe = self._safe_float(metrics.get("sharpe"), 0.0)
        result.turnover = self._safe_float(metrics.get("turnover"), 1.0)
        result.skew = self._safe_float(metrics.get("skewness"), 0.0)
        result.kurtosis = self._safe_float(metrics.get("kurtosis"), 0.0)
        trl = metrics.get("longCount") or metrics.get("trackRecordLength")
        result.track_record_length = int(trl) if trl else config.DEFAULT_TRACK_RECORD_LENGTH
        result.valid = True
        self.result_cache[cache_key] = result
        return result

    async def _check_correlation(self, alpha_id) -> float:
        """Realized self-correlation (max abs) from the platform. This is the
        authoritative decorrelation signal, unlike the structural string proxy."""
        if not alpha_id:
            return 0.0
        try:
            resp = await self.network.request("GET", f"/alphas/{alpha_id}/correlations/self")
            data = resp.get("json")
            records = []
            if isinstance(data, dict):
                records = data.get("records") or data.get("results") or []
            elif isinstance(data, list):
                records = data
            values = []
            for row in records:
                if isinstance(row, dict):
                    v = row.get("correlation", row.get("value", row.get("max")))
                elif isinstance(row, (list, tuple)) and row:
                    v = row[-1]
                else:
                    v = row
                if isinstance(v, (int, float)) and math.isfinite(v):
                    values.append(abs(float(v)))
            return max(values) if values else 0.0
        except Exception as e:
            logger.error(f"Correlation check failed for {alpha_id}: {e}")
            return 0.0

    async def _is_near_duplicate_loser(self, canonical) -> bool:
        if len(self.loser_exprs) < 20:
            return False
        refs = self.loser_exprs[-400:]
        sim = await asyncio.to_thread(self.deflation.structural_similarity, canonical, refs)
        return sim >= config.NEAR_DUPLICATE_SIMILARITY

    # --- evaluation ----------------------------------------------------------
    async def _evaluate_population(self, candidates, allow_grid=True):
        prepared = []
        for cand in candidates:
            expr = cand.get("expression")
            if not expr:
                continue
            ok, canonical = SyntaxValidator.parse_and_validate(expr)
            if not ok or SyntaxValidator.is_tautology(canonical):
                continue
            universe = cand.get("universe") or random.choice(config.UNIVERSES)
            decay = cand.get("decay")
            if decay is None:
                decay = random.choice(config.DECAYS)
            key = f"{canonical}|{universe}|{decay}"
            if key in self.evaluated_canon:
                continue
            self.evaluated_canon.add(key)
            prepared.append((canonical, universe, decay))

        filtered = []
        for canonical, universe, decay in prepared:
            if await self._is_near_duplicate_loser(canonical):
                continue
            filtered.append((canonical, universe, decay))
        if not filtered:
            return []

        tasks = [asyncio.create_task(self._simulate_alpha(c, u, d)) for c, u, d in filtered]
        self._active_tasks.update(tasks)
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                self._active_tasks.discard(t)

        valid = [r for r in results if r.valid]
        async with self._state_lock:
            for r in results:
                if not r.valid:
                    self.loser_exprs.append(r.expression)
        if not valid:
            return []

        # Single fitness path. num_trials is the GLOBAL count of completed
        # simulations (the multiple-testing penalty), var_trials is the empirical
        # per-period variance of historical Sharpes.
        num_trials = max(2, await self.db.count_trials() + len(valid))
        var_trials = self._estimate_var_trials()
        dsr_scores = [
            self.deflation.calculate_dsr(r.sharpe, r.skew, r.kurtosis, r.track_record_length, num_trials, var_trials)
            for r in valid
        ]
        elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
        elite_exprs = [rec["expression"] for rec in self.population[:elite_count]]
        adjusted = self.deflation.calculate_orthogonal_fitness_batch(
            [r.expression for r in valid], elite_exprs, dsr_scores
        )

        new_records = []
        winners = []
        for r, dsr, adj in zip(valid, dsr_scores, adjusted):
            depth = _ast_depth(r.expression)
            fitness = adj - config.PARSIMONY_COEFFICIENT * depth
            qualifies = r.sharpe >= config.MIN_SHARPE and r.turnover <= config.MAX_TURNOVER
            max_corr = await self._check_correlation(r.alpha_id) if qualifies else None
            record = {
                "expression": r.expression, "universe": r.universe, "decay": r.decay,
                "sharpe": r.sharpe, "turnover": r.turnover, "dsr": dsr, "fitness": fitness,
                "ast_depth": depth, "skew": r.skew, "kurtosis": r.kurtosis,
                "track_record_length": r.track_record_length, "alpha_id": r.alpha_id,
                "max_correlation": max_corr,
            }
            new_records.append(record)
            if qualifies and (max_corr is None or max_corr <= config.MAX_SELF_CORRELATION):
                winners.append(r.expression)

        async with self._state_lock:
            for rec in new_records:
                self.population.append(rec)
                self.history_exprs.append(rec["expression"])
                self.history_scores.append(rec["sharpe"])
                if rec["sharpe"] < config.MIN_SHARPE:
                    self.loser_exprs.append(rec["expression"])
                await self.db.save_alpha(
                    rec["expression"], rec["universe"], rec["decay"], rec["alpha_id"],
                    self.generation, rec["sharpe"], rec["turnover"], rec["fitness"],
                    rec["ast_depth"], rec["skew"], rec["kurtosis"],
                    rec["track_record_length"], rec["max_correlation"],
                )

        if allow_grid:
            for winner_expr in winners:
                if winner_expr in self.grid_searched:
                    continue
                self.grid_searched.add(winner_expr)
                grid = self._build_grid_candidates(winner_expr)
                # allow_grid=False prevents unbounded recursive grid expansion.
                await self._evaluate_population(grid, allow_grid=False)

        return new_records

    def _build_grid_candidates(self, expression):
        """Grid for a winning alpha: vary universe x decay, and -- when the
        expression is group_neutralize(inner, GROUP) -- also strip and re-wrap
        the inner logic across every neutralization in config.NEUTRALIZATIONS,
        so a better grouping for this logic isn't missed. evaluated_canon dedup
        in _evaluate_population skips the winner's own already-tested combo.
        """
        inner, _group = _split_group_neutralize(expression)
        if inner is not None:
            expr_variants = [f"group_neutralize({inner}, {n})" for n in config.NEUTRALIZATIONS]
        else:
            expr_variants = [expression]
        return [
            {"expression": expr, "universe": u, "decay": d}
            for expr in expr_variants
            for u in config.UNIVERSES
            for d in config.DECAYS
        ]

    # --- selection -----------------------------------------------------------
    def _nsga_ii_sort(self, population):
        n = len(population)
        if n <= 1:
            for r in population:
                r["rank"] = 0
                r["distance"] = float("inf")
            return list(population)

        objs = [(r.get("fitness", float("-inf")), r.get("turnover", 1.0)) for r in population]

        def dominates(i, j):
            fi, ti = objs[i]
            fj, tj = objs[j]
            return (fi >= fj and ti <= tj) and (fi > fj or ti < tj)

        dominated = [[] for _ in range(n)]
        dom_count = [0] * n
        fronts = [[]]
        for p in range(n):
            for q in range(n):
                if p == q:
                    continue
                if dominates(p, q):
                    dominated[p].append(q)
                elif dominates(q, p):
                    dom_count[p] += 1
            if dom_count[p] == 0:
                population[p]["rank"] = 0
                fronts[0].append(p)

        i = 0
        while fronts[i]:
            nxt = []
            for p in fronts[i]:
                for q in dominated[p]:
                    dom_count[q] -= 1
                    if dom_count[q] == 0:
                        population[q]["rank"] = i + 1
                        nxt.append(q)
            i += 1
            fronts.append(nxt)
        fronts.pop()

        for r in population:
            r["distance"] = 0.0
        for front in fronts:
            if not front:
                continue
            for m in range(2):
                front.sort(key=lambda idx: objs[idx][m])
                population[front[0]]["distance"] = float("inf")
                population[front[-1]]["distance"] = float("inf")
                lo = objs[front[0]][m]
                hi = objs[front[-1]][m]
                span = hi - lo
                if span == 0:
                    continue
                for k in range(1, len(front) - 1):
                    population[front[k]]["distance"] += (objs[front[k + 1]][m] - objs[front[k - 1]][m]) / span

        ordered = []
        for front in fronts:
            front.sort(key=lambda idx: -population[idx]["distance"])
            ordered.extend(front)
        return [population[idx] for idx in ordered]

    def _select_parents(self):
        if len(self.population) < 2:
            return None
        def tournament():
            k = min(config.TOURNAMENT_SIZE, len(self.population))
            contenders = random.sample(self.population, k)
            return min(contenders, key=lambda r: (r.get("rank", 0), -r.get("distance", 0.0)))
        return tournament(), tournament()

    # --- bootstrap & main loop ----------------------------------------------
    async def _bootstrap_population(self):
        top = await self.db.get_top_population(config.POPULATION_SIZE)
        if top:
            num_trials = max(2, await self.db.count_trials())
            var_trials = self._estimate_var_trials()
            for row in top:
                (expr, universe, decay, sharpe, turnover, depth, skew,
                 kurtosis, trl, max_corr, alpha_id, _fitness) = row
                depth = depth or _ast_depth(expr)
                # Recompute fitness with the SAME function used for live alphas
                # so resumed and freshly-evaluated members are directly comparable.
                dsr = self.deflation.calculate_dsr(
                    sharpe, skew or 0.0, kurtosis if kurtosis is not None else 0.0,
                    trl or config.DEFAULT_TRACK_RECORD_LENGTH, num_trials, var_trials,
                )
                fitness = dsr - config.PARSIMONY_COEFFICIENT * depth
                self.population.append({
                    "expression": expr, "universe": universe, "decay": decay,
                    "sharpe": sharpe, "turnover": turnover, "dsr": dsr, "fitness": fitness,
                    "ast_depth": depth, "skew": skew or 0.0, "kurtosis": kurtosis if kurtosis is not None else 0.0,
                    "track_record_length": trl or config.DEFAULT_TRACK_RECORD_LENGTH,
                    "alpha_id": alpha_id or "", "max_correlation": max_corr,
                })
                self.evaluated_canon.add(f"{expr}|{universe}|{decay}")
            logger.info(f"Resumed population with {len(self.population)} alphas.")
            return

        seeds = await self.llm.generate_seeds(config.POPULATION_SIZE)
        if not seeds:
            seeds = [self.llm.fill_template(t) for t in config.QUANT_TEMPLATES]
        candidates = [{"expression": s, "universe": random.choice(config.UNIVERSES),
                       "decay": random.choice(config.DECAYS)} for s in seeds]
        await self._evaluate_population(candidates, allow_grid=False)
        logger.info(f"Seeded initial population with {len(self.population)} alphas.")

    async def run(self, generations=None):
        await self.initialize()
        generations = generations or config.GENERATIONS
        if not self.population:
            await self._bootstrap_population()

        for gen in range(generations):
            self.generation = gen
            self.population = self._nsga_ii_sort(self.population)[: config.POPULATION_SIZE]
            if not self.population:
                logger.warning("Population collapsed to empty; re-seeding.")
                await self._bootstrap_population()
                continue

            best = self.population[0]
            logger.info(f"Gen {gen}: pop={len(self.population)} best_fitness={best['fitness']:.4f} "
                        f"best_sharpe={best['sharpe']:.3f} submissions={self.submission_count}")

            elite_count = max(1, int(config.POPULATION_SIZE * config.ELITISM_RATIO))
            offspring = []

            if gen > 0 and gen % config.EXPERIENCE_RESEED_INTERVAL == 0:
                seeds = await self.llm.generate_seeds(config.EXPERIENCE_RESEED_COUNT)
                offspring.extend({"expression": s, "universe": random.choice(config.UNIVERSES),
                                  "decay": random.choice(config.DECAYS)} for s in seeds)

            target = max(1, config.POPULATION_SIZE - elite_count)
            guard = 0
            while len(offspring) < target and guard < target * 8:
                guard += 1
                parents = self._select_parents()
                if not parents:
                    break
                p1, p2 = parents
                child = self.genetic.crossover(p1["expression"], p2["expression"])
                if random.random() < config.MUTATION_RATE:
                    child = self.genetic.mutate(child)
                offspring.append({"expression": child,
                                  "universe": random.choice(config.UNIVERSES),
                                  "decay": random.choice(config.DECAYS)})

            # Elites are carried over implicitly: they stay in self.population and
            # are NEVER re-simulated. Only genuinely new offspring are evaluated.
            await self._evaluate_population(offspring, allow_grid=True)
            self.population = self._nsga_ii_sort(self.population)[: config.POPULATION_SIZE]

        logger.info("Factory run complete.")


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    factory = AlphaFactory()
    try:
        await factory.run()
    finally:
        await factory.shutdown()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())