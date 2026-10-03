"""Forge2 evidence-bound campaign adapter.

Loads recorded joint availability and active leaves before engine construction;
preflights every candidate at the simulation seam, enables typed/local genetic
search and advisory queue ordering, and provides an optional third NSGA-II
objective (platform-fitness × conservative field-multiplier PROXY).

run(generations=N) runs TO N. A resumed burst targets checkpoint+burst length.
No code in this module certifies theme valuation or authorizes alpha submission.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import forge2_config as F2
from forge2_expression import field_tokens, BUILTIN_GROUPS, type_errors
from forge2_storage import atomic_json
from collections import Counter


def _identifier_tokens(expression):
    out, cur = [], []
    for ch in expression or "":
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


class PyramidResolver:
    """expression -> pyramid boost, via the forge2 field meta map."""

    def __init__(self, meta_path):
        self.multiplier_by_token = {}
        try:
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        self.meta = meta
        self.field_metadata = meta.get("field_metadata", {})
        for expr_id, m in (meta.get("fields") or {}).items():
            mult = float(m.get("multiplier") or 1.0)
            # Register verified base fields only, never operator identifiers.
            bases = m.get("base") or ([expr_id] if expr_id.isidentifier() else [])
            for base in bases:
                self.multiplier_by_token[base] = float(m.get("multiplier") or 1.0)
        for fid, m in self.field_metadata.items():
            if m.get("type") != "GROUP":
                self.multiplier_by_token[fid] = float(m.get("multiplier") or 1.0)

    def boost(self, expression, universe=None):
        """Dominant-field multiplier, clamped to [1, cap], raised to gamma.
        Unknown fields resolve to a neutral 1.0 (never a penalty)."""
        values = []
        axes = self.meta.get("axes", {})
        for tok in field_tokens(expression):
            if tok in BUILTIN_GROUPS or self.field_metadata.get(tok,{}).get("type")=="GROUP":
                continue
            if tok not in self.multiplier_by_token:
                return 1.0
            mult = self.multiplier_by_token[tok]
            if universe and self.field_metadata:
                matches=[v for v in self.field_metadata[tok].get("availability",[])
                         if v[0]==axes.get("region") and int(v[1])==int(axes.get("delay",-1)) and v[2]==universe]
                mult = float(matches[-1][4]) if matches else 1.0
            values.append(mult)

        if not values:
            return 1.0
        # Conservative field-value proxy, NOT a verified platform theme rule.
        boost = min(max(min(values), 1.0), F2.PYRAMID_BOOST_CAP)
        return boost ** F2.PYRAMID_GAMMA


def apply_config_overrides(config_module, region, delay):
    """Point the stock engine at the campaign axes (findings #3, #4, #8, #9)."""
    config_module.DEFAULT_REGION = region
    config_module.DEFAULT_DELAY = int(delay)
    config_module.DECAYS = list(F2.DECAYS)
    config_module.DECAY_TO_INDEX = {d: i for i, d in enumerate(config_module.DECAYS)}
    universes = list(F2.UNIVERSES_BY_REGION.get(region) or [])
    if os.getenv("FORGE2_EXPERIMENTAL_UNIVERSES", "").strip() == "1":
        universes += [u for u in F2.EXPERIMENTAL_UNIVERSES.get(region, [])
                      if u not in universes]
    if universes:
        config_module.UNIVERSES = universes
        config_module.PRIMARY_UNIVERSE = F2.PRIMARY_UNIVERSE_BY_REGION.get(
            region, universes[0])
    return config_module


def configure_evidence(config,resolver):
    if not resolver.field_metadata:
        raise ValueError("Factory requires normalized field metadata with joint availability")
    if resolver.meta.get("axes") != {"region":config.DEFAULT_REGION,"delay":config.DEFAULT_DELAY}:
        raise ValueError("Campaign axes and vocabulary axes do not match")
    config.FIELD_METADATA = resolver.field_metadata
    config.SEMANTIC_ACTIVE_FIELDS = set(resolver.meta.get("active_fields") or resolver.field_metadata)
    config.SEMANTIC_MUTATION_ENABLED = True
    config.VECTOR_PROJECTION_MUTATION_ENABLED = True
    config.THIRD_OBJECTIVE_ENABLED = F2.THIRD_OBJECTIVE_ENABLED
    config.SURROGATE_PRIORITIZATION_ENABLED = True
    config.DEFLATION_MAX_TRIALS = 0
    config.SAFE_SIMULATION_WRITES = True
    config.RESEARCH_OFFLINE_ONLY=F2.RESEARCH_OFFLINE_ONLY
    config.MAX_DISPATCHES=F2.MAX_DISPATCHES
    config.MAX_POLL_OPERATIONS=F2.MAX_POLL_OPERATIONS
    config.SEARCH_MAX_NODES=F2.SEARCH_MAX_NODES
    config.SEARCH_MAX_CALLS=F2.SEARCH_MAX_CALLS
    config.SEARCH_MAX_DEPTH=F2.SEARCH_MAX_DEPTH
    config.SEARCH_MAX_FIELDS=F2.SEARCH_MAX_FIELDS
    config.SEARCH_MAX_WINDOW=F2.SEARCH_MAX_WINDOW
    config.BASKET_SELECTION_ENABLED=F2.BASKET_SELECTION_ENABLED
    config.BASKET_MAX_CORRELATION=F2.BASKET_MAX_CORRELATION
    config.BASKET_MIN_RESIDUAL=F2.BASKET_MIN_RESIDUAL
    config.BASKET_DATASET_FRACTION=F2.BASKET_DATASET_FRACTION
    config.BASKET_EXPLORATION_FRACTION=F2.BASKET_EXPLORATION_FRACTION
    config.BASKET_MIN_OVERLAP=F2.BASKET_MIN_OVERLAP
    observed = resolver.meta.get("observed_universes") or []
    if observed:
        config.UNIVERSES = list(observed)
        config.PRIMARY_UNIVERSE = resolver.meta["primary_universe"]


def build_factory(meta_path):
    """Construct Forge2Factory (imports the repo engine lazily so env vars set
    by the campaign runner are honored by config's import-time loading)."""
    import orchestrator  # noqa: repo module
    import random
    random.seed(F2.RANDOM_SEED)

    resolver = PyramidResolver(meta_path)
    config = orchestrator.config
    configure_evidence(config,resolver)
    from forge2_policy import fingerprint,guard
    current=fingerprint(config,resolver.meta.get("catalog_hash"),os.getenv("WQ_OPERATORS_PATH",F2.OPERATORS_PATH))

    class Forge2Factory(orchestrator.AlphaFactory):
        """AlphaFactory with the pyramid-multiplier objective (finding #2)."""

        def __init__(self):
            super().__init__()
            self.preflight_rejections = Counter()
            from forge2_experiments import ExperimentLedger
            self.experiment_ledger=ExperimentLedger(self.db.db_name+".experiments.sqlite")
            self.experiment_context={"catalog":resolver.meta.get("catalog_hash"),
                "identity_version":"syntax_preserving_v2","operators":__import__("hashlib").sha256(json.dumps(current["policy"]["operator_schema"],sort_keys=True).encode()).hexdigest(),
                "region":config.DEFAULT_REGION,"delay":config.DEFAULT_DELAY}
            self.scoring_policy_hash=current["fingerprint"]
            self.trial_ledger = None
            ledger_path=os.getenv("FORGE2_TRIAL_LEDGER")
            if ledger_path:
                from forge2_trials import TrialLedger
                self.trial_ledger=TrialLedger(ledger_path)
                self.trial_context=str(config.DEFAULT_REGION)+"_d"+str(config.DEFAULT_DELAY)
                self.trial_ledger.import_history(self.db.db_name,self.trial_context)

        async def _simulate_alpha(self, expression, universe, decay):
            from syntax_validator import SyntaxValidator
            ok, canonical=SyntaxValidator.parse_and_validate(expression)
            errors=[] if ok and not SyntaxValidator.is_tautology(canonical) else ["INVALID_SYNTAX_OR_TAUTOLOGY"]
            errors += type_errors(expression,resolver.field_metadata)
            from forge2_search import budget_errors
            errors += budget_errors(expression,config.SEARCH_MAX_NODES,config.SEARCH_MAX_CALLS,
                config.SEARCH_MAX_DEPTH,config.SEARCH_MAX_FIELDS,config.SEARCH_MAX_WINDOW)
            if decay not in config.DECAYS:
                errors.append("OUTSIDE_CONFIGURED_DECAY_GRID")
            for token in set(field_tokens(expression)) - BUILTIN_GROUPS:
                meta=resolver.field_metadata.get(token)
                if meta is None:
                    continue  # type checker already reports UNKNOWN_FIELD
                available=meta.get("availability",[])
                if not any(v[0]==config.DEFAULT_REGION and int(v[1])==config.DEFAULT_DELAY and v[2]==universe for v in available):
                    errors.append("UNOBSERVED_SETTINGS:"+token)
            if errors:
                for error in set(errors):
                    self.preflight_rejections[error.split(":")[0]] += 1
                self._remember_failure(expression,"preflight:"+";".join(errors))
                return orchestrator.SimulationResult(expression=expression,universe=universe,decay=decay,valid=False)
            return await super()._simulate_alpha(canonical,universe,decay)

        def _nsga_ii_sort(self, population):
            for rec in population:
                value=config.worldquant_fitness(rec.get("sharpe",0),rec.get("returns",0),rec.get("turnover",1))
                rec["expected_value"] = max(0.0,value) * resolver.boost(rec["expression"],rec.get("universe"))
            return super()._nsga_ii_sort(population)

        def _composite_fitness(self, adjusted_dsr, depth, sharpe, oos_sharpe,
                               expression):
            fitness = super()._composite_fitness(
                adjusted_dsr, depth, sharpe, oos_sharpe, expression)
            if fitness > 0 and not F2.THIRD_OBJECTIVE_ENABLED:
                fitness *= resolver.boost(expression)
            return fitness

    policy_path=os.getenv("FORGE2_POLICY_PATH")
    if policy_path:
        import sqlite3
        from forge2_policy import fingerprint,guard
        db_path=Path(os.getenv("BRAINFORGE_DB","brain_memory.db"))
        has_rows=False
        if db_path.exists():
            conn=sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True)
            try:has_rows=conn.execute("SELECT COUNT(*) FROM alpha_population WHERE sharpe IS NOT NULL").fetchone()[0]>0
            finally:conn.close()
        current=fingerprint(config,resolver.meta.get("catalog_hash"),os.getenv("WQ_OPERATORS_PATH",F2.OPERATORS_PATH))
        guard(policy_path,current,has_rows)
    return Forge2Factory()


def _burst_generation_target(generations):
    """Bound the burst under either run(generations) interpretation by adding
    the checkpointed generation counter when one is readable."""
    ckpt = os.getenv("WQ_CHECKPOINT", "")
    if ckpt and Path(ckpt).exists():
        try:
            data = json.loads(Path(ckpt).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("generation", "gen", "current_generation"):
                    v = data.get(key)
                    if isinstance(v, int) and v >= 0:
                        return v + int(generations)
        except (OSError, ValueError):
            pass
    return int(generations)


def run_burst(region, delay, generations, meta_path):
    import asyncio
    import logging

    import config as repo_config

    apply_config_overrides(repo_config, region, delay)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("forge2").info(
        "burst start region=%s delay=%s generations=%s vocab=%s db=%s",
        region, delay, generations,
        os.getenv("WQ_FIELD_CATALOG"), os.getenv("BRAINFORGE_DB"))

    factory = build_factory(meta_path)
    target = _burst_generation_target(generations)

    async def _run():
        try:
            await factory.run(generations=target)
        finally:
            atomic_json(Path(meta_path).with_name("forge2_preflight_report.json"),
                        {"rejections":dict(factory.preflight_rejections),
                         "policy":F2.FITNESS_POLICY_VERSION})
            shutdown = getattr(factory, "shutdown", None)
            if callable(shutdown):
                result = shutdown()
                if asyncio.iscoroutine(result):
                    await result

    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    asyncio.run(_run())


def main():
    ap = argparse.ArgumentParser(description="Forge2 single burst runner")
    ap.add_argument("--region", required=True)
    ap.add_argument("--delay", type=int, required=True)
    ap.add_argument("--generations", type=int, default=F2.BURST_GENERATIONS)
    ap.add_argument("--meta", default="forge2_field_meta.json")
    ap.add_argument("--repo", default=".", help="path to the BrainForge repo")
    args = ap.parse_args()
    repo = str(Path(args.repo).resolve())
    if repo not in sys.path:
        sys.path.insert(0, repo)
    run_burst(args.region, args.delay, args.generations, args.meta)


if __name__ == "__main__":
    main()
