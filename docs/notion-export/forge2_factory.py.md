Part of **Forge v2 — Consultant Overhaul (Sept 2026)**. The ONLY module that touches the repo engine, through two narrow, verbatim-verified seams: (1) post-import config overrides that pin the campaign's region/delay/decay/universe axes, and (2) an `AlphaFactory` subclass overriding `_composite_fitness` to multiply positive fitness by the dominant field's pyramid multiplier — so NSGA-II optimizes expected platform value with zero changes to engine selection code. Launched per burst by forge2_[campaign.py](http://campaign.py) in a fresh interpreter.
```python
"""Forge2 factory: pyramid-aware fitness + per-burst engine configuration.

This is the ONLY module that touches the repo engine, and it does so through
two narrow, verbatim-verified seams:

  1. apply_config_overrides(region, delay): mutates the imported repo `config`
     module AFTER import (build_settings reads module globals at call time, so
     DEFAULT_REGION / DEFAULT_DELAY / DECAYS / UNIVERSES overrides take effect
     everywhere, including build_simulation_payload). DECAY_TO_INDEX is rebuilt
     because config computes it at import.
  2. Forge2Factory overrides AlphaFactory._composite_fitness(adjusted_dsr,
     depth, sharpe, oos_sharpe, expression) -- the single fitness definition
     used by BOTH live evaluation and resume -- multiplying POSITIVE fitness by
     the dominant field's pyramid multiplier ** gamma (finding #2). NSGA-II
     then optimizes expected platform value with zero changes to selection.

Run this file directly for one burst (normally launched by forge2_campaign):

    python forge2_factory.py --region USA --delay 1 --generations 8 \
        --meta forge2_field_meta.json --repo /path/to/BrainForge

Requires the BrainForge repo on sys.path and live credentials in .env.
Environment (set by the campaign runner BEFORE python starts, so the repo
config's import-time loading sees them):
    WQ_FIELD_CATALOG / WQ_SEED_POOL -> campaign vocabulary files
    BRAINFORGE_DB / WQ_CHECKPOINT   -> per-campaign state isolation

Burst-length note: AlphaFactory.run(generations=...) semantics on resumed
checkpoints are engine-internal; we read the campaign checkpoint's generation
counter (when present) and pass current+burst so the burst is bounded under
either "run N more" or "run to N" interpretation.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import forge2_config as F2


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
        for expr_id, m in (meta.get("fields") or {}).items():
            mult = float(m.get("multiplier") or 1.0)
            # register the row id's bare tokens AND its base fields, so both
            # compound vocabulary entries and GA-bred descendants resolve.
            for tok in _identifier_tokens(expr_id):
                self.multiplier_by_token.setdefault(tok, mult)
            for base in m.get("base") or []:
                prev = self.multiplier_by_token.get(base, 1.0)
                self.multiplier_by_token[base] = max(prev, mult)

    def boost(self, expression):
        """Dominant-field multiplier, clamped to [1, cap], raised to gamma.
        Unknown fields resolve to a neutral 1.0 (never a penalty)."""
        counts = {}
        for tok in _identifier_tokens(expression):
            if tok in self.multiplier_by_token:
                counts[tok] = counts.get(tok, 0) + 1
        if not counts:
            return 1.0
        dominant = max(counts.items(), key=lambda kv: kv[1])[0]
        mult = self.multiplier_by_token.get(dominant, 1.0)
        boost = min(max(mult, 1.0), F2.PYRAMID_BOOST_CAP)
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


def build_factory(meta_path):
    """Construct Forge2Factory (imports the repo engine lazily so env vars set
    by the campaign runner are honored by config's import-time loading)."""
    import orchestrator  # noqa: repo module

    resolver = PyramidResolver(meta_path)

    class Forge2Factory(orchestrator.AlphaFactory):
        """AlphaFactory with the pyramid-multiplier objective (finding #2)."""

        def _composite_fitness(self, adjusted_dsr, depth, sharpe, oos_sharpe,
                               expression):
            fitness = super()._composite_fitness(
                adjusted_dsr, depth, sharpe, oos_sharpe, expression)
            if fitness > 0:
                fitness *= resolver.boost(expression)
            return fitness

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
```