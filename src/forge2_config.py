"""Forge2 -- consultant-era configuration for the BrainForge generator overhaul.

This file is the single source of tuning truth for the Forge2 layer. It is
stdlib-only and importable standalone (no repo imports), so every Forge2 module
and the smoke test can load it in any environment.

Design map (finding -> knob):
  #1  two-tier vocabulary        -> CANDIDATE_POOL_MAX / ACTIVE_* knobs
  #2  pyramid-aware objective    -> PYRAMID_GAMMA / PYRAMID_BOOST_CAP
  #3  region axis + preflight    -> CAMPAIGN_AXES / availability filters
  #4  delay-0 allocation         -> CAMPAIGN_AXES weights (delay-0 share)
  #5  vector projections         -> VECTOR_* knobs
  #6  GROUP neutralization keys  -> GROUP_KEYS_* knobs
  #7  new gates (2Y/realization) -> GATE_* (scout + reporting alignment)
  #8  decay fast end             -> DECAYS
  #9  universe grid              -> UNIVERSES_BY_REGION
  #10 sample efficiency          -> bandit knobs (Thompson over datasets)
  #11 semantic neighborhoods     -> ACTIVE_PER_DATASET / TERM_SPREAD_* / SEMANTIC_*
  #12 return decorrelation + ENB -> RETURN_DECORR / ENB knobs
  #13 Model category inclusion   -> (no exclusion) + ACTIVE_PER_DATASET budget
  #14 effective trials           -> DEFLATION_TRIALS_MODE (P1 note; capped default)
"""

import hashlib
import os
from pathlib import Path

# --- Paths -------------------------------------------------------------------
# Offline merged catalog produced from the platform snapshot (2 Sep 2026).
CATALOG_PATH = str(Path(__file__).resolve().parent / "brain_fields_merged.json")
# Live operator metadata. Either the repo's operators.json (a list of operator
# dicts) or a snapshot directory of per-operator json files. Both supported.
OPERATORS_PATH = str(Path(__file__).resolve().parent / "operators.json")
OPERATORS_DIR_FALLBACK = ""  # optional: dir of <op>.json files from the snapshot
# Root directory for per-campaign working state (db, checkpoint, vocab files).
CAMPAIGN_ROOT = str(Path(__file__).resolve().parent / "campaigns")

# --- Campaign axes (findings #3, #4) ------------------------------------------
# Each campaign pins (region, delay) for a burst of generations. The scheduler
# allocates bursts by weight; delay-0 gets a real, enforced share of the budget
# (the old engine logged SUBMISSION_MIN_DELAY0_FRACTION but never enforced it).
# ~60% USA/d1 (deepest catalog, pyramid multipliers), ~20% EUR/d1 (13,399
# frontier fields, near-zero crowding), ~20% USA/d0 (82.5% frontier density,
# stricter fitness bar but disproportionate payoff).
CAMPAIGN_AXES = [
    {"region": "USA", "delay": 1, "weight": 0.60},
    {"region": "EUR", "delay": 1, "weight": 0.20},
    {"region": "USA", "delay": 0, "weight": 0.20},
]
BURST_GENERATIONS = 8          # generations per burst before rotation
MAX_BURSTS = 0                 # 0 = run forever (ctrl-c to stop)

# --- Two-tier vocabulary (finding #1) -----------------------------------------
# Tier 1: ranked candidate pool (everything worth considering, per campaign).
# Tier 2: rotating ACTIVE set actually exposed to the GA (locality preserved).
CANDIDATE_POOL_MAX = 20000
ACTIVE_DATASET_ARMS = 40       # datasets sampled per rotation (bandit arms)
ACTIVE_PER_DATASET = 12        # max fields admitted per dataset (family budget,
                               # also the finding-#13 within-family cap)
ACTIVE_SET_MAX = 700           # hard cap on total vocabulary rows emitted
ACTIVE_MIN_PER_ARM = 3         # guarantee locality: >=3 siblings per dataset
# Frontier filters (mirror the deep-research definition).
POOL_MIN_COVERAGE = 0.05       # keep sparse event fields (ts_backfill handles them)
BACKFILL_BELOW_COVERAGE = 0.60 # coverageMode=backfill under this (harvester parity)
POOL_MAX_ALPHA_COUNT = 2000    # drop only truly saturated fields from the pool
FRONTIER_MULTIPLIER = 1.5      # stats/reporting definition of "frontier"
FRONTIER_MAX_ALPHAS = 50

# --- Priority score (consultant version; findings #2, #13) --------------------
W_VALUE = 0.30                 # value = normalized (pyramidMultiplier - 1)
W_MATURITY = 0.25              # sweet-spot proven-but-uncrowded curve
W_COVERAGE = 0.20
W_HISTORY = 0.15
W_SIMPLICITY = 0.10
SIMPLICITY_BY_TYPE = {"MATRIX": 1.0, "VECTOR": 0.75}  # VECTOR upgraded (7 lenses)
PROVEN_FULL_AT = 5
CROWD_PENALTY = 0.6
CROWD_FLOOR = 0.25
PYRAMID_GAMMA = 1.0            # score *= multiplier ** gamma
# NO Model-category exclusion (finding #13): the 1.8-1.9x datasets
# (chart_cnn_alpha, ai_equity_alpha, mmp_nlp_sentiment, ml_factor_proj) are
# admitted; ACTIVE_PER_DATASET is the within-family correlation budget.

# --- Pyramid objective shaping (finding #2) ------------------------------------
# Forge2Factory multiplies POSITIVE composite fitness by
#   boost = clamp(dominant_field_multiplier, 1.0, PYRAMID_BOOST_CAP) ** PYRAMID_GAMMA
# so NSGA-II optimizes expected platform value, not raw fitness.
PYRAMID_BOOST_CAP = 2.0

# --- Vector projections (finding #5) -------------------------------------------
# Baseline vec_avg comes free from the stock loader (VECTOR rows). These extra
# projections are emitted as compound MATRIX rows for the top vector fields.
VECTOR_EXTRA_PROJECTIONS = ["vec_stddev", "vec_range", "vec_max", "vec_min", "vec_sum", "vec_count"]
VECTOR_EXTRA_PER_FIELD = 2     # projections beyond vec_avg per vector field
VECTOR_FIELDS_EXPANDED = 80    # how many top vector fields get extra projections
VECTOR_DISAGREEMENT = True     # emit vec_stddev/vec_avg coefficient-of-variation
VECTOR_DISAGREEMENT_MAX = 40   # cap on disagreement compound rows

# --- Term-structure & semantic spreads (finding #11) ---------------------------
TERM_SPREAD_MAX_TOTAL = 60     # subtract(near, far) compound rows per campaign
TERM_SPREAD_MAX_PER_FAMILY = 2
SEMANTIC_SPREAD_MAX_TOTAL = 24 # subtract(long_side, short_side) compound rows

# --- GROUP neutralization keys (finding #6) ------------------------------------
GROUP_KEYS_MAX = 12            # top GROUP fields (by coverage) used as keys
GROUP_KEYS_MIN_COVERAGE = 0.60
GROUP_KEY_TEMPLATE_FRACTION = 0.25  # share of seed templates using a custom key

# --- Axes: decay / universes (findings #8, #9) ---------------------------------
DECAYS = [0, 1, 2, 3, 5, 10, 15, 20]   # full platform grid incl. fast end
UNIVERSES_BY_REGION = {
    # Conservative, platform-confirmed core grids. EXPERIMENTAL_UNIVERSES are
    # appended only when FORGE2_EXPERIMENTAL_UNIVERSES=1 (probe first).
    "USA": ["TOP3000", "TOP1000", "TOP500", "TOP200"],
    "EUR": ["TOP2500", "TOP1200", "TOP800", "TOP600", "TOP400"],
    "ASI": ["MINVOL1M", "ILLIQUID_MINVOL1M"],
}
EXPERIMENTAL_UNIVERSES = {
    "USA": ["TOP2000U", "TOPSP500", "TOPDIV3000", "MINVOL1M", "ILLIQUID_MINVOL1M"],
    "EUR": ["ILLIQUID_MINVOL1M"],
}
PRIMARY_UNIVERSE_BY_REGION = {"USA": "TOP3000", "EUR": "TOP2500", "ASI": "MINVOL1M"}

# --- Consultant scoring gates (finding #7) --------------------------------------
# Optimization proxies + reporting. Hard enforcement stays with BRAIN is.checks
# (already fail-closed in the engine) and submission_scout.
GATE_SHARPE = 1.58
GATE_SHARPE_2Y = 1.58          # recency gate (cutoff observed 20 Jul 2026)
GATE_PNL_REALIZATION = 20.0    # high-turnover gate (higher = better)
HIGH_TURNOVER_THRESHOLD = 0.35 # realization gate applies above this turnover
RECENCY_WINDOW_DAYS = 504      # ~2 trading years

# --- Bandit (finding #10) -------------------------------------------------------
BANDIT_STATE_FILE = "forge2_bandit_state.json"
BANDIT_PRIOR_BETA = 19.0       # ~5% base keeper-rate prior
BANDIT_PRIOR_MULT_WEIGHT = 3.0 # optimism from (avg multiplier - 1)
BANDIT_PRIOR_CROWD_WEIGHT = 2.0  # pessimism from log10(1 + avg alphaCount)
BANDIT_SUCCESS_SHARPE = 1.25   # DB row counts as a success at/above this
BANDIT_TURNOVER_BAND = (0.01, 0.70)
BANDIT_COUNT_CAP = 500.0       # posterior evidence cap; no implied time decay
BANDIT_EXPLORE_FLOOR = 4       # arms always drawn uniformly at random

# --- Engine config overrides applied per burst ----------------------------------
# Applied to the imported repo config module by forge2_factory (attr overrides)
# or via env (documented next to each). Values chosen from the deep research.
OVERRIDE_ENV = {
    "WQ_HARVEST_VOCAB_MAX": "900",          # >= ACTIVE_SET_MAX (never re-throttle)
    "WQ_HARVEST_VOCAB_PER_CAT": "900",      # pool already balances categories
    "WQ_HARVEST_VOCAB_MAX_ALPHAS": "5000",  # frontier filter applied upstream
    "WQ_SEED_POOL_MAX_PER_FIELD": "3",
    "WQ_RETURN_DECORR_SELECTION": "1",      # finding #12: return-based decorr ON
    "WQ_DEFLATION_MAX_TRIALS": "0",      # uncapped observed trials; not inferred independence
    "WQ_NEUT_MUTATION": "1",                # neutralization-style mutation ON
    "WQ_SEED_COVERAGE_FIRST": "1",
}
RETURN_DECORR_ENABLED = True
ENB_REPORT_TOP_N = 25          # elite alphas in the run-level ENB report

# --- Misc ----------------------------------------------------------------------
SEED_TEMPLATE_MAX_PER_FIELD = 4
RANDOM_SEED = int(os.getenv("FORGE2_RANDOM_SEED", "20261002")) #             # set int for reproducible vocabulary builds

# Offline-evidence-driven improvements. Legacy engine defaults remain unchanged.
FIELD_EXPLORATION_FRACTION = 0.30
THIRD_OBJECTIVE_ENABLED = os.getenv("FORGE2_THIRD_OBJECTIVE", "1") == "1"
# Second-pass engineering controls: conservative budgets, explicit diagnostics.
RESEARCH_OFFLINE_ONLY=os.getenv("FORGE2_OFFLINE_ONLY","1")!="0"
MAX_DISPATCHES=int(os.getenv("FORGE2_MAX_DISPATCHES","0")) # 0: no inferred lifetime quota
MAX_POLL_OPERATIONS=1000
SEARCH_MAX_NODES=160
SEARCH_MAX_CALLS=32
SEARCH_MAX_DEPTH=18
SEARCH_MAX_FIELDS=8
SEARCH_MAX_WINDOW=1500
BASKET_SELECTION_ENABLED=os.getenv("FORGE2_BASKET_SELECTION","1")=="1"
BASKET_MAX_CORRELATION=.80
BASKET_MIN_RESIDUAL=.10
BASKET_DATASET_FRACTION=.40
BASKET_EXPLORATION_FRACTION=.20
BASKET_MIN_OVERLAP=60
_policy_files = sorted(Path(__file__).parent.glob("*.py"))
_policy_digest = hashlib.sha256(b"".join(p.read_bytes() for p in _policy_files if p.exists())).hexdigest()[:16]
FITNESS_POLICY_VERSION = "forge2-v4-quant-research-" + _policy_digest + "-third" + str(int(THIRD_OBJECTIVE_ENABLED))
OVERRIDE_ENV.update({"WQ_VOCAB_ISOLATED":"1", "WQ_SEED_QUANT_FRACTION":"0"})
