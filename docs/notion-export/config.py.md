```python
import json
import math
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required configuration/metadata is missing or malformed."""


# --- Credentials & endpoints -------------------------------------------------
WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
# A manually-pasted session cookie (fallback). Prefer programmatic auth below.
WQ_COOKIE = os.getenv("WQ_COOKIE", "")
# Programmatic authentication (preferred): the network engine can mint fresh
# cookies automatically instead of waiting for a human to paste one.
WQ_EMAIL = os.getenv("WQ_EMAIL", "")
WQ_PASSWORD = os.getenv("WQ_PASSWORD", "")

# --- Dataset-scoped mining (single-dataset campaign) ------------------------
# OPTIONAL, FULLY REVERSIBLE OVERLAY. Set WQ_DATASET_ID to a BRAIN dataset id
# (e.g. "earnings4") to CONSTRAIN the whole engine to that one dataset. Leave it
# EMPTY and the engine behaves EXACTLY as before -- the static multi-dataset
# dictionary, QUANT_TEMPLATES and broad breadth-first search are all preserved
# and untouched. The constraint only changes which fields are FED to that same
# core logic at runtime; it deletes none of it. When set:
#   * field_harvester.py pulls /data-fields filtered to ONLY this dataset, so
#     data_fields.json / seed_pool.json contain only its fields;
#   * the harvested catalog REPLACES the static DATA_DICTIONARY / FIELD_GROUPS
#     for this run, so breadth-first seeding AND genetic mutation stay inside
#     the dataset (they can never reintroduce close/returns/etc.);
#   * the typed multi-group QUANT_TEMPLATES are switched off (SEED_QUANT_FRACTION
#     defaults to 0), since they expect a broad cross-dataset field universe --
#     a single dataset seeds via seed_pool.json + breadth-first SIMPLE_TEMPLATES.
# Re-run field_harvester.py after changing this so the scoped catalog is rebuilt.
WQ_DATASET_ID = os.getenv("WQ_DATASET_ID", "").strip()
RESTRICT_TO_DATASET = bool(WQ_DATASET_ID)

# --- Seed generation: grammar backbone + optional pluggable LLM -------------
# The deterministic grammar/template engine (llm_seed_generator.py) is the
# ALWAYS-ON seed source. An LLM is an OPTIONAL idea-injector that is OFF by
# default: set SEED_LLM_ENABLED=1 and supply the matching provider key to turn
# it on. This guarantees a weak or missing model can never bottleneck seeding.
SEED_LLM_ENABLED = os.getenv("SEED_LLM_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# Provider: "gemini" | "openai" | "anthropic" | "ollama".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
# Per-provider credentials (only the active provider's key is required).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Sensible default model per provider; LLM_MODEL env overrides for any of them.
_LLM_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "ollama": "llama3.1",
}
LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or _LLM_DEFAULT_MODELS.get(LLM_PROVIDER, "gemini-2.5-flash")
# When the LLM is enabled, the maximum fraction of a seed batch it may supply;
# the grammar engine always fills the rest.
LLM_SEED_FRACTION = float(os.getenv("LLM_SEED_FRACTION", "0.5"))

# --- Reproducibility ---------------------------------------------------------
# Set RANDOM_SEED in the environment to an integer for reproducible runs.
_seed_env = os.getenv("RANDOM_SEED", "").strip()
RANDOM_SEED = int(_seed_env) if _seed_env else None

# --- Data field dictionaries -------------------------------------------------
PRICE_FIELDS = ["close", "vwap", "open", "high", "low"]
VOLATILITY_FIELDS = ["implied_volatility_call_30", "implied_volatility_put_30", "implied_volatility_call_60", "implied_volatility_put_60", "implied_vol_skew"]
MACRO_FIELDS = ["mdl53_jc5_5year", "mdl53_jc5_1year", "mdl53_jc5_10year"]
SIZE_FIELDS = ["cap", "assets", "sales"]
FUNDAMENTAL_FIELDS = ["est_eps", "bookvalue_ps", "sales", "assets", "est_eps_growth", "est_sales_revision"]
SENTIMENT_FIELDS = ["news_short_interest", "news_management_tone", "news_controversy_index"]
MOMENTUM_FIELDS = ["volume", "returns", "adjfactor"]
RELATIONSHIP_FIELDS = ["rel_ret_cust", "rel_ret_part", "rel_ret_supp"]

DATA_DICTIONARY = PRICE_FIELDS + VOLATILITY_FIELDS + MACRO_FIELDS + SIZE_FIELDS + FUNDAMENTAL_FIELDS + SENTIMENT_FIELDS + MOMENTUM_FIELDS + RELATIONSHIP_FIELDS
FIELD_GROUPS = {
    "price": PRICE_FIELDS,
    "volatility": VOLATILITY_FIELDS,
    "macro": MACRO_FIELDS,
    "size": SIZE_FIELDS,
    "fundamental": FUNDAMENTAL_FIELDS,
    "sentiment": SENTIMENT_FIELDS,
    "momentum": MOMENTUM_FIELDS,
    "relationship": RELATIONSHIP_FIELDS,
}

# Per-group seeding weights (Upgrade #2). Over-sample SLOW / ALTERNATIVE data
# (fundamental, sentiment, relationship, macro) relative to fast price/volume
# fields: slow data has lower turnover -> higher BRAIN fitness, and is less
# crowded -> more uncorrelated returns -> higher portfolio score. Applied to
# every {FIELD} fill and combined with experience-memory penalties.
SEED_FIELD_GROUP_WEIGHTS = {
    # Rebalanced (B5). The original 2.5/2.0 slow-data tilt manufactured a
    # low-turnover monoculture: almost everything was born well under the ~1%
    # submittable floor, fighting the turnover band downstream. These weights
    # keep a MILD tilt toward uncrowded slow/alt data (still > price/momentum)
    # but no longer crush turnover at birth, so more seeds land in the
    # submittable mid-turnover range. Tune toward the old values to favour
    # decorrelation over submittability, or flatter to favour turnover.
    "fundamental": 1.6,
    "sentiment": 1.5,
    "relationship": 1.5,
    "macro": 1.2,
    "size": 1.0,
    "volatility": 1.2,
    "price": 1.0,
    "momentum": 1.0,
}

# --- Harvested field vocabulary (data-first) --------------------------------
# field_harvester.py writes data_fields.json (the full, priority-ranked LIVE
# catalog). We fold the top-ranked harvested fields into the LIVE vocabulary so
# that EVERY downstream consumer -- typed-placeholder QUANT_TEMPLATES,
# breadth-first seeding, AND the genetic mutation operator -- samples the real,
# de-crowded catalog instead of the small static dictionary below. Without this
# the data-first seed pool only shapes generation 0 and is then bred straight
# back out by crossover/mutation that can reach only the static fields.
FIELD_CATALOG_PATH = os.getenv("WQ_FIELD_CATALOG", str(Path(__file__).with_name("data_fields.json")))
# In a dataset-scoped run every field shares ONE category, so the broad-catalog
# per-category cap (20) would fold only the top 20 fields into DATA_DICTIONARY /
# FIELD_GROUPS -- starving breadth-first seeding AND the genetic mutation pool to
# 20 of the dataset's hundreds of fields (the seed pool would then shape only
# gen-0 and get bred straight back out). Open both caps wide when scoped so the
# whole curated dataset reaches every downstream consumer; keep the tight
# defaults for full-catalog runs.
HARVEST_VOCAB_MAX_FIELDS = int(os.getenv("WQ_HARVEST_VOCAB_MAX", "500" if RESTRICT_TO_DATASET else "120"))   # total harvested fields admitted
HARVEST_VOCAB_PER_CATEGORY = int(os.getenv("WQ_HARVEST_VOCAB_PER_CAT", "500" if RESTRICT_TO_DATASET else "20"))  # per-category cap (diversify)
HARVEST_VOCAB_MAX_ALPHAS = int(os.getenv("WQ_HARVEST_VOCAB_MAX_ALPHAS", "200"))   # skip crowded fields


def _category_to_group(category):
    """Map a live BRAIN data-category name onto the closest template field group
    (price/volatility/fundamental/sentiment/macro/size/relationship). Keyword /
    substring matching keeps it robust to the exact catalog spelling. Returns
    None when nothing fits -- such fields still enter DATA_DICTIONARY (so the
    {FIELD} pass and mutation reach them), they just don't feed TYPED placeholders.
    """
    c = (category or "").lower()
    if any(k in c for k in ("sentiment", "news", "social", "short interest", "buzz")):
        return "sentiment"
    if any(k in c for k in ("fundamental", "earning", "analyst", "balance", "cash flow", "income", "estimate")):
        return "fundamental"
    if any(k in c for k in ("option", "volatil", "implied")):
        return "volatility"
    if any(k in c for k in ("macro", "econom", "rate", "risk")):
        return "macro"
    if any(k in c for k in ("institution", "ownership", "supply", "relation", "insider", "peer", "holder")):
        return "relationship"
    if any(k in c for k in ("price", "volume", "trade")):
        return "price"
    if any(k in c for k in ("size", "market cap")):
        return "size"
    return None


# Backfill window (trading days) for sparse / event fields. Earnings &
# announcement data updates on a ~quarterly cadence, so a SHORT backfill leaves
# names NaN between events -- the cross-section collapses to the few live names
# and weight concentrates ("Weight is too strongly concentrated / too few
# instruments are assigned weight"). A ~1-year window carries each name's last
# reported value across several events, densifying the cross-section. Applied to
# the RAW field (inside rank), which is what actually adds breadth. Kept SEPARATE
# from the {LOOKBACK_*} smoothing windows so densification (long backfill) never
# forces the smoother long too -- over-smoothing crushes turnover below the 1%
# submittable floor.
HARVEST_BACKFILL_WINDOW = int(os.getenv("WQ_HARVEST_BACKFILL_WINDOW", "252"))


def _harvested_field_expr(field_id, ftype, mode):
    """Type-correct SCALAR expression for a raw harvested field: VECTOR fields are
    collapsed with vec_avg, sparse/event fields are wrapped in ts_backfill so the
    signal persists between updates, MATRIX/direct fields are used as-is. This is
    what makes it safe to drop harvested fields straight into templates and the
    mutation pool."""
    expr = field_id
    if ftype == "VECTOR":
        expr = f"vec_avg({field_id})"
    if mode == "backfill":
        expr = f"ts_backfill({expr}, {HARVEST_BACKFILL_WINDOW})"
    return expr


def _load_harvested_vocabulary():
    """Read data_fields.json and return (field_exprs, group_to_exprs). Silent empty
    fallback (-> static dictionary only) when the catalog is missing/malformed, so
    a fresh checkout still runs."""
    path = Path(FIELD_CATALOG_PATH)
    if not path.exists():
        return [], {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    if not isinstance(rows, list):
        return [], {}
    rows = sorted(rows, key=lambda r: r.get("priorityScore", 0) or 0, reverse=True)
    field_exprs = []
    group_to_exprs = defaultdict(list)
    per_cat = Counter()
    seen = set()
    for r in rows:
        if len(field_exprs) >= HARVEST_VOCAB_MAX_FIELDS:
            break
        fid = r.get("id")
        ftype = (r.get("type") or "").upper()
        if not fid or ftype not in ("MATRIX", "VECTOR"):
            continue  # GROUP fields are neutralization keys, not signals
        if (r.get("alphaCount") or 0) > HARVEST_VOCAB_MAX_ALPHAS:
            continue
        category = r.get("category")
        if per_cat[category] >= HARVEST_VOCAB_PER_CATEGORY:
            continue
        expr = _harvested_field_expr(fid, ftype, r.get("coverageMode"))
        if expr in seen:
            continue
        seen.add(expr)
        per_cat[category] += 1
        field_exprs.append(expr)
        group = _category_to_group(category)
        if group:
            group_to_exprs[group].append(expr)
    return field_exprs, dict(group_to_exprs)


_HARVESTED_FIELD_EXPRS, _HARVESTED_GROUP_EXPRS = _load_harvested_vocabulary()

# Fold harvested fields into the live vocabulary (ADDITIVE: the static fields
# stay, so a checkout with no catalog still works and proven static shapes
# survive). Typed placeholders pull from FIELD_GROUPS; the {FIELD} pass and the
# genetic mutation pool pull from DATA_DICTIONARY.
if RESTRICT_TO_DATASET and _HARVESTED_FIELD_EXPRS:
    # Dataset-scoped campaign: REPLACE the static multi-dataset universe with the
    # harvested (single-dataset) catalog so no downstream consumer -- breadth-first
    # seeding or genetic mutation -- can wander outside the target dataset. This is
    # a runtime swap only; the static dictionary above is left intact so emptying
    # WQ_DATASET_ID instantly restores the general-purpose generator. All original
    # group keys are kept (emptied) so typed-placeholder lookups never KeyError;
    # only the harvested groups are populated. Harvested entries are already
    # type-correct (VECTOR fields wrapped in vec_avg, sparse fields in ts_backfill),
    # so they drop straight into templates and the mutation pool.
    FIELD_GROUPS = {_grp: [] for _grp in FIELD_GROUPS}
    for _grp, _exprs in _HARVESTED_GROUP_EXPRS.items():
        FIELD_GROUPS[_grp] = list(dict.fromkeys(_exprs))
    DATA_DICTIONARY = list(dict.fromkeys(_HARVESTED_FIELD_EXPRS))
elif RESTRICT_TO_DATASET:
    # Restricted, but no harvested catalog yet -- run field_harvester.py first.
    # Fall back to the static dictionary so importing config (and the harvester
    # itself, which imports config) never crashes; the constraint takes effect
    # once data_fields.json exists.
    print("[config] WQ_DATASET_ID set but data_fields.json is empty/missing -- "
          "run field_harvester.py first to scope the field universe.")
else:
    for _grp, _exprs in _HARVESTED_GROUP_EXPRS.items():
        FIELD_GROUPS.setdefault(_grp, [])
        FIELD_GROUPS[_grp] = list(dict.fromkeys(FIELD_GROUPS[_grp] + _exprs))
    DATA_DICTIONARY = list(dict.fromkeys(DATA_DICTIONARY + _HARVESTED_FIELD_EXPRS))

QUANT_TEMPLATES = [
    # 1: Cross-Sectional Volatility Risk Premium (VRP) Arbitrage
    "group_neutralize(rank(ts_decay_linear(ts_zscore({FUNDAMENTAL}, {LOOKBACK_LONG}) * (ts_std_dev({PRICE}, {LOOKBACK_SHORT}) / ts_mean({VOLATILITY}, {LOOKBACK_SHORT})), {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # 2: Fractal Trend-State Momentum (Hurst Approximation)
    "group_neutralize(ts_rank(ts_delta({PRICE}, {LOOKBACK_SHORT}) * (ts_std_dev({PRICE}, {LOOKBACK_LONG}) / (ts_std_dev({PRICE}, {LOOKBACK_SHORT}) * sqrt({LOOKBACK_LONG} / {LOOKBACK_SHORT}))), {LOOKBACK_LONG}), {NEUTRALIZATION})",
    # 3: Information Theoretic Sentiment Decay (Pseudo-Entropy)
    "group_neutralize(rank(ts_mean({SENTIMENT}, {LOOKBACK_SHORT}) / ts_std_dev({SENTIMENT}, {LOOKBACK_LONG})) * ts_zscore(ts_delta({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    # 4: Advanced Statistical Arbitrage via Macro-Conditioned Co-integration
    "group_neutralize(ts_decay_linear(rank(ts_zscore({FUNDAMENTAL} / {PRICE}, {LOOKBACK_LONG})) * ts_corr({PRICE}, {MACRO}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    # 5: Options Flow Skew vs. Fundamental Reality
    "group_neutralize(rank(ts_rank({VOLATILITY}, {LOOKBACK_SHORT}) * -1) * ts_rank(ts_delta({FUNDAMENTAL}, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    # 6: Supply-Chain Orthogonal Momentum
    "group_neutralize(rank(ts_av_diff(ts_decay_linear({MOMENTUM}, {LOOKBACK_SHORT}), {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 7: Asymmetric Volatility Breakout with Volume Validation
    "group_neutralize(trade_when(ts_zscore({MOMENTUM}, {LOOKBACK_SHORT}) > 1.0, ts_rank(ts_delta({PRICE}, {LOOKBACK_SHORT}) / ts_std_dev({PRICE}, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), -1), {NEUTRALIZATION})",
    # 8: Fundamental Acceleration (Second Derivative) Scoring
    "group_neutralize(rank(ts_delta(ts_delta({FUNDAMENTAL}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # 9: Non-Linear Mean Reversion via Densified Group Scaling
    "group_scale(group_zscore(ts_rank(-ts_av_diff({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION}), {NEUTRALIZATION})",
    # 10: Sentiment-Adjusted Implied Volatility Surface Roll
    "group_neutralize(ts_decay_linear(rank(ts_delta({SENTIMENT}, {LOOKBACK_SHORT})) * ts_zscore(-{VOLATILITY}, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    # --- Canonical structural primitives (economically-motivated base shapes:
    # reversal, momentum, value, quality, low-vol, volume-price divergence,
    # mean-reversion, etc.). These are NOT lifted from any published formula set
    # -- in particular NOT the 2015 "101 Formulaic Alphas", whose literal
    # short-horizon signals are long since arbitraged away. They are
    # intentionally GENERIC, SIMPLE skeletons; the edge does not live in the
    # skeleton. It comes from (a) the breadth of data fields the engine plugs
    # in (price, fundamental, sentiment, relationship, macro, volatility, ...)
    # and (b) the GP + inline refinement that branch and evolve these shapes.
    # The seeds therefore favour robustness and diversity over pre-optimized
    # complexity.
    # 11: Short-term cross-sectional reversal
    "group_neutralize(-ts_zscore(ts_delta({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_LONG}), {NEUTRALIZATION})",
    # 12: Time-series momentum (long minus short horizon)
    "group_neutralize(rank(ts_delta({PRICE}, {LOOKBACK_LONG}) - ts_delta({PRICE}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # 13: Low-volatility anomaly
    "group_neutralize(-rank(ts_std_dev({MOMENTUM}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 14: Value / earnings yield
    "group_neutralize(rank(ts_zscore({FUNDAMENTAL} / {PRICE}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 15: Quality / fundamental growth
    "group_neutralize(rank(ts_delta({FUNDAMENTAL}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 16: Volume-price divergence
    "group_neutralize(-rank(ts_corr(ts_delta({PRICE}, {LOOKBACK_SHORT}), ts_delta({MOMENTUM}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # 17: Risk-adjusted momentum
    "group_neutralize(rank(ts_delta({PRICE}, {LOOKBACK_LONG}) / ts_std_dev({PRICE}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 18: VWAP / price mean-reversion
    "group_neutralize(-ts_zscore({PRICE} - ts_mean({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    # 19: Liquidity-scaled reversal
    "group_neutralize(-rank(ts_delta({PRICE}, {LOOKBACK_SHORT}) * ts_zscore({MOMENTUM}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 20: Sentiment-confirmed momentum
    "group_neutralize(rank(ts_zscore({SENTIMENT}, {LOOKBACK_LONG}) * ts_zscore(ts_delta({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # --- Category-aware + turnover-controlled templates (data-first overhaul).
    # These exploit the harvested data families now folded into the typed
    # placeholders, and use the WorldQuant turnover lever trade_when(<gate>,
    # <signal>, -1) to throttle rebalancing. Turnover is half of BRAIN's fitness
    # (sqrt(|returns|/max(turnover,0.125)) * Sharpe), so gating churn is one of
    # the highest-ROI structural moves available.
    # 21: Turnover-gated value (re-trade only when the volatility regime is active)
    "group_neutralize(trade_when(ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}) > 0, rank(ts_zscore({FUNDAMENTAL} / {PRICE}, {LOOKBACK_LONG})), -1), {NEUTRALIZATION})",
    # 22: Turnover-gated reversal (re-trade only on volume spikes)
    "group_neutralize(trade_when(ts_zscore({MOMENTUM}, {LOOKBACK_SHORT}) > 1, -ts_zscore(ts_delta({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_LONG}), -1), {NEUTRALIZATION})",
    # 23: Analyst / earnings revision drift (slow fundamental, decayed)
    "group_neutralize(rank(ts_decay_linear(ts_delta({FUNDAMENTAL}, {LOOKBACK_LONG}), {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # 24: News / sentiment shock, gated to fire only on a real move
    "group_neutralize(trade_when(ts_zscore({SENTIMENT}, {LOOKBACK_SHORT}) > 1, rank(ts_zscore({SENTIMENT}, {LOOKBACK_LONG})), -1), {NEUTRALIZATION})",
    # 25: Relationship / peer relative-strength (supply-chain, institutional)
    "group_neutralize(rank(ts_zscore({RELATIONSHIP}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # 26: Macro-conditioned low-volatility, churn-damped via long decay
    "group_neutralize(ts_decay_linear(-rank(ts_std_dev({MOMENTUM}, {LOOKBACK_LONG})) * ts_zscore({MACRO}, {LOOKBACK_LONG}), {LOOKBACK_LONG}), {NEUTRALIZATION})"
]

# --- Breadth-first "wide and simple" discovery templates --------------------
# The highest-ROI alphas on BRAIN are usually a SIMPLE transform of an
# under-used data field, not a complex expression on a crowded one. These
# minimal one-field skeletons are applied to EVERY field in DATA_DICTIONARY by
# the breadth-first seeding pass (llm_seed_generator._materialize_breadth_first)
# so niche fields get a fair shot BEFORE the richer QUANT_TEMPLATES above. Each
# uses a single {FIELD} placeholder that the pass pins to one specific field.
# NOTE: this pays off in proportion to how diverse DATA_DICTIONARY is -- expand
# the field catalog with niche datasets (analyst, announcement, news, options,
# institutional, ...) to get the most out of it.
SIMPLE_TEMPLATES = [
    "group_neutralize(rank({FIELD}), {NEUTRALIZATION})",
    "group_neutralize(-rank({FIELD}), {NEUTRALIZATION})",
    "group_neutralize(zscore({FIELD}), {NEUTRALIZATION})",
    "group_neutralize(rank(ts_delta({FIELD}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    "group_neutralize(-rank(ts_delta({FIELD}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    "group_neutralize(rank(ts_zscore({FIELD}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    "group_neutralize(rank(ts_rank({FIELD}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    "group_neutralize(-rank(ts_mean({FIELD}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    "group_neutralize(rank(ts_av_diff({FIELD}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # Structurally DIVERSE shapes (monoculture breaker): deliberately NOT
    # group_neutralize(rank(...)). Breadth-first seeding samples across these so
    # generation 0 is not ~90% one skeleton. Each is a single-field economic
    # primitive in a distinct structural form; invalid combinations are dropped
    # by the validator, so adding a slightly-off shape is harmless.
    "group_neutralize(ts_zscore({FIELD}, {LOOKBACK_LONG}), {NEUTRALIZATION})",
    "group_neutralize(-ts_zscore({FIELD}, {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(ts_decay_linear(ts_delta({FIELD}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(sign(ts_delta({FIELD}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    "group_neutralize(ts_delta(ts_delta({FIELD}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(-ts_av_diff({FIELD}, {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(trade_when(ts_zscore({FIELD}, {LOOKBACK_SHORT}) > 1, ts_zscore({FIELD}, {LOOKBACK_LONG}), -1), {NEUTRALIZATION})",
    "group_neutralize(ts_decay_linear(ts_zscore({FIELD}, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
]
# Lead seeding with the breadth-first pass (one simple alpha per field). Set to
# False to fall back to the original random-fill behaviour over QUANT_TEMPLATES.
BREADTH_FIRST_SEEDING = True

# --- Data-first seed pool (field_harvester.py output) -----------------------
# field_harvester.py ranks the LIVE BRAIN catalog and writes seed_pool.json: a
# diversified, de-crowded set of RAW data fields, each with ready-to-fill simple
# templates. When the file is present, the seed generator LEADS with these (one
# simple alpha per high-priority field) before the static SIMPLE_TEMPLATES /
# DATA_DICTIONARY pass, so seeding tracks the live catalog instead of the
# hardcoded dictionary. Delete the file (or set SEED_POOL_FIRST=False) to fall
# back to the static breadth-first behaviour.
SEED_POOL_PATH = os.getenv("WQ_SEED_POOL", str(Path(__file__).with_name("seed_pool.json")))
SEED_POOL_FIRST = True

# --- Generation-0 field-coverage seeding (breadth over depth) ---------------
# Generation 0's job is to EXPLORE the whole field universe, not to crowd the
# seed budget onto the top-ranked handful of fields. Two knobs guarantee that:
#   * SEED_COVERAGE_FIRST runs the breadth-first "one simple alpha per field"
#     pass over the ENTIRE dictionary BEFORE the priority-ranked seed pool spends
#     the budget on extra variants of the top fields. Without it, when there are
#     more fields than the seed budget, the priority-ordered seed pool exhausts
#     the budget on the top ~(budget / SEED_POOL_MAX_PER_FIELD) fields and the
#     long tail is never seeded -- the gen-0 field-crowding bug (e.g. only
#     73 of 371 dataset-scoped fields reached).
#   * SEED_GEN0_COVER_ALL_FIELDS lifts the generation-0 seed budget to at least
#     the field count (max(POPULATION_SIZE, len(DATA_DICTIONARY))) so the
#     coverage pass is never truncated by a population smaller than the field
#     universe. Those extra seeds are all SIMULATED at generation 0 (so every
#     field is actually tested) and NSGA-II then truncates the survivors back to
#     POPULATION_SIZE for generation 1. Set =0 to keep gen 0 at POPULATION_SIZE.
SEED_COVERAGE_FIRST = os.getenv("WQ_SEED_COVERAGE_FIRST", "1").strip().lower() in ("1", "true", "yes", "on")
SEED_GEN0_COVER_ALL_FIELDS = os.getenv("WQ_SEED_GEN0_COVER_ALL_FIELDS", "1").strip().lower() in ("1", "true", "yes", "on")

# --- Generation-0 structural budget (seed diversity) ------------------------
# With a large harvested catalog the data-first seed pool has FAR more fields
# than POPULATION_SIZE, so a one-alpha-per-field pass would fill the ENTIRE
# initial population with single-field "rank/zscore" shapes and starve every
# multi-field / turnover-gated / term-structure-spread template (the rich
# QUANT_TEMPLATES and the harvester's spread seeds) out of generation 0 --
# exactly the shapes the genetic engine is slowest to rediscover by crossover.
# Two knobs fix that:
#   * SEED_QUANT_FRACTION reserves a slice of the population for QUANT_TEMPLATES
#     so structurally diverse, economically-motivated shapes are GUARANTEED at
#     gen 0 (set 0 to restore the old last-resort-only behaviour).
#   * SEED_POOL_MAX_PER_FIELD lets each seed-pool field emit up to K validated
#     templates (so its family + term-structure-spread templates actually take
#     part) instead of exactly one.
SEED_QUANT_FRACTION = float(os.getenv("WQ_SEED_QUANT_FRACTION", "0.0" if RESTRICT_TO_DATASET else "0.18"))
SEED_POOL_MAX_PER_FIELD = int(os.getenv("WQ_SEED_POOL_MAX_PER_FIELD", "2"))

# --- Alpha-quality overhaul knobs (upgrades A-D) ----------------------------
# Everything below has a safe in-code default in field_harvester.py /
# orchestrator.py; it is surfaced here so the generator can be retuned WITHOUT
# editing those modules. Re-run field_harvester.py after changing any (A)/(B)
# knob so seed_pool.json / data_fields.json are regenerated.
#
# (B) Crowding penalty used by field_harvester.py when ranking fields: a
# multiplicative dampener in [FIELD_CROWDING_FLOOR, 1] that pushes heavily-used
# fields (many existing alphas / users) down the priority list so the seed pool
# favours uncrowded data. 0 disables it; a higher PENALTY punishes crowding more.
FIELD_CROWDING_PENALTY = float(os.getenv("WQ_FIELD_CROWDING_PENALTY", "0.6"))
FIELD_CROWDING_FLOOR = float(os.getenv("WQ_FIELD_CROWDING_FLOOR", "0.25"))
# (A) Max term-structure spread seeds added per field by the harvester.
SEED_MAX_SPREAD_TEMPLATES = int(os.getenv("WQ_SEED_MAX_SPREAD_TEMPLATES", "2"))
# (A) Field-id / category stems that route a field to a tailored template family
# (field_harvester._family_of). Add stems to teach the harvester new families.
FAMILY_OPTIONS_STEMS = ["atmiv", "exerniv", "_iv", "div", "clshv", "orhv",
                        "straddle", "strap", "ernmv", "impernmv", "slope",
                        "erneff", "dtex", "ern4_",
                        # Descriptive live-vocabulary tokens. earnings4 returns
                        # English ids (aggregate_option_open_interest,
                        # best_fit_implied_*), so the stems must match those too.
                        "implied", "option", "open_interest", "atm", "skew",
                        "volatil", "vega"]
FAMILY_ANALYST_STEMS = ["guidance", "estimate", "consensus", "eps", "ebitda",
                        "sales", "netprofit", "cfo", "fcf", "capex",
                        "bookvalue", "revision",
                        # Live earnings/announcement vocabulary -> analyst seed
                        # templates (levels + revisions + spreads) in the harvester.
                        "announcement", "percent_move", "pct_move", "forecast",
                        "earnings"]
FAMILY_SENTIMENT_STEMS = ["sentiment", "snt1", "snt_", "news", "social", "buzz",
                          "mood", "focusrank", "stockrank", "torpedo"]
# (D) Genetic spread/combination mutation (orchestrator GeneticEngine): combine
# two same-group fields into a near-minus-far spread. False disables it entirely
# (mutation AND decorrelation refinement).
SPREAD_MUTATION_ENABLED = os.getenv("WQ_SPREAD_MUTATION", "1").strip().lower() in ("1", "true", "yes", "on")
# (C) Per-template decay prior strength: probability a seed uses the decay
# suggested by its data family (fast options/vol -> low, analyst/fundamental ->
# high, sentiment -> mid) instead of a uniform random decay. 0 => always random
# (pure exploration); 1 => always use the prior. The refiner still sweeps decay.
SEED_DECAY_PRIOR_STRENGTH = float(os.getenv("WQ_SEED_DECAY_PRIOR_STRENGTH", "0.5"))
# (C) Stems mapping an expression to a decay speed (orchestrator._suggest_decay).
DECAY_FAST_STEMS = ["atmiv", "exerniv", "_iv", "clshv", "orhv", "straddle",
                    "strap", "ernmv", "impernmv", "slope", "ern4_",
                    "implied", "atm", "option", "skew", "open_interest"]
DECAY_SLOW_STEMS = ["guidance", "estimate", "consensus", "eps", "ebitda",
                    "sales", "netprofit", "cfo", "fcf", "capex", "bookvalue",
                    "fundamental",
                    "announcement", "earnings", "pct_move", "percent_move",
                    "forecast"]
DECAY_MID_STEMS = ["sentiment", "snt1", "snt_", "news", "social", "buzz",
                  "mood", "focusrank", "stockrank", "torpedo"]

# --- Operator-field affinity (SOFT economic prior) -------------------------
# Root cause of "the generator randomly fits operators to fields": both seeding
# and the genetic mutation pair operators with data fields with NO awareness of
# what a field MEANS, so an operator can land on a field it makes no economic
# sense for. This injects a SOFT prior -- each data family has operators it is
# naturally suited to (PREFERRED, up-weighted in sampling) and operators that
# rarely make sense for it (DISCOURAGED, down-weighted). It only BIASES sampling;
# nothing is forbidden here, so the generator stays fully general and still
# explores every combination. The handful of GENUINELY meaningless combos is
# hard-blocked separately (AFFINITY_HARD_* + syntax_validator). Set
# WQ_AFFINITY_ENABLED=0 to restore the old pure-random pairing.
AFFINITY_ENABLED = os.getenv("WQ_AFFINITY_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
# Sampling multipliers: a PREFERRED (operator, family) pairing is up-weighted, a
# DISCOURAGED one down-weighted, everything else neutral (1.0). Kept mild so the
# bias steers without collapsing diversity (raise PREFERRED / lower DISCOURAGED
# to bias harder; set both to 1.0 to neutralize without unwiring it).
AFFINITY_PREFERRED_WEIGHT = float(os.getenv("WQ_AFFINITY_PREFERRED_WEIGHT", "2.5"))
AFFINITY_DISCOURAGED_WEIGHT = float(os.getenv("WQ_AFFINITY_DISCOURAGED_WEIGHT", "0.3"))
# Extra stems (beyond the FAMILY_*_STEMS above) identifying the price/volume
# family for affinity resolution.
FAMILY_PRICE_VOLUME_STEMS = ["close", "open", "high", "low", "vwap", "volume",
                             "returns", "adjfactor", "cap", "turnover", "vol_"]
# Earnings4 TRUE step/event fields: the per-event move history (ern4_ernmv1..12)
# and the event-timing pair (ernmnth, nexterntod). The dataset doc is explicit
# that on these a change operator catches the EARNINGS EVENT itself -- which is
# exactly the signal -- so they must PREFER ts_delta/ts_zscore rather than
# inherit the options_vol family's blanket ts_delta avoidance. Kept narrow: the
# slow earnings-move NORMALISERS (absavgernmv, ernmvstdev) and the rolling
# strike/tenor fields are deliberately excluded (options_vol + the hard guard
# already handle those).
FAMILY_EARNINGS_EVENT_STEMS = ["ern4_ernmv", "ernmnth", "nexterntod",
                               # Live descriptive per-event move ids.
                               "pct_move_announcement", "announcement_percent_move",
                               "post_earnings"]
# Field family -> (preferred operators, discouraged operators). Operator names
# match case-insensitively; an operator in neither list is neutral. The lists
# encode each family's economic logic:
#   * options_vol -> cross-sectional ranking, term-structure spreads, decay;
#     NOT first-differences (a rolling IV chain delta is a fake jump) or
#     correlation between mechanically-derived series.
#   * analyst/fundamental -> slow levels + REVISIONS (a delta here IS the
#     signal), value ratios; NOT field-to-field correlation.
#   * sentiment -> level / zscore, event gating; NOT correlation / regression.
#   * price_volume -> the classic ts momentum / reversal / correlation toolkit.
OPERATOR_AFFINITY = {
    "options_vol": {
        # Enriched with the high-ROI BRAIN options/vol operators confirmed by the
        # WorldQuant options seminar + IV term-structure research: vec_avg FIRST
        # (reduce the vector), group_rank over rank (low-coverage friendly),
        # ts_backfill (persist sparse earnings/forecast fields), trade_when
        # (event/regime turnover gating) and vector_neut / group_vector_neut
        # (orthogonalise against a base-IV risk factor).
        "prefer": ["rank", "group_rank", "zscore", "ts_rank", "ts_zscore",
                   "ts_mean", "ts_decay_linear", "ts_backfill", "subtract",
                   "divide", "vec_avg", "trade_when", "vector_neut",
                   "group_vector_neut"],
        "avoid": ["ts_delta", "ts_av_diff", "ts_corr"],
    },
    "earnings_event": {
        # Per-event earnings move history + event timing (STEP fields). Doc:
        # "what ts_delta is really catching is the event, not a slow move -- that
        # is often just what you want." So PREFER the change/rank ops and backfill
        # the sparse per-event series; correlation between mechanically-derived
        # earnings fields is meaningless.
        "prefer": ["ts_delta", "ts_zscore", "ts_rank", "rank", "group_rank",
                   "ts_backfill", "ts_decay_linear", "divide"],
        "avoid": ["ts_corr"],
    },
    "analyst": {
        # Earnings-estimate/forecast fields: REVISIONS and drift are the signal
        # (ts_delta is correct here), backfilled + decayed for the slow PEAD
        # horizon, group_rank for low-coverage, trade_when to gate on the
        # earnings event.
        "prefer": ["rank", "group_rank", "ts_delta", "ts_zscore",
                   "ts_decay_linear", "ts_backfill", "divide", "ts_mean",
                   "ts_regression", "trade_when"],
        "avoid": ["ts_corr", "sign"],
    },
    "fundamental": {
        "prefer": ["rank", "ts_delta", "ts_zscore", "divide", "ts_decay_linear"],
        "avoid": ["ts_corr"],
    },
    "sentiment": {
        "prefer": ["rank", "zscore", "ts_zscore", "ts_mean", "trade_when",
                   "ts_decay_linear"],
        "avoid": ["ts_corr", "ts_regression"],
    },
    "macro": {
        "prefer": ["ts_zscore", "ts_mean", "subtract", "rank", "ts_corr"],
        "avoid": ["sign"],
    },
    "relationship": {
        "prefer": ["rank", "ts_zscore", "ts_mean", "ts_decay_linear"],
        "avoid": [],
    },
    "price_volume": {
        "prefer": ["ts_delta", "ts_rank", "ts_zscore", "ts_corr", "ts_std_dev",
                   "rank", "ts_mean", "ts_av_diff", "ts_decay_linear"],
        "avoid": [],
    },
}


# --- Live-catalog field -> family map (robust routing) ----------------------
# Stem-only routing silently NO-OPS when the live dataset's field ids do not
# contain our hardcoded stems. earnings4 is the textbook case: its live ids are
# descriptive English (pct_move_announcement_1, best_fit_implied_announcement_
# effect, aggregate_option_open_interest, ...) and matched NONE of the cryptic
# ern4_* stems, so field_family returned None for the ENTIRE population and all
# affinity / decay / hard-guard steering was off -- operators were paired with
# fields blindly (the "randomly fits operators to fields" complaint). This map
# is built from the HARVESTED catalog (data_fields.json) and routes each field
# by keywords in BOTH its id and its human-readable description, so routing
# tracks whatever the live dataset actually calls its fields.
_FAMILY_KEYWORDS = [
    ("earnings_event", ("announcement", "post earnings", "post-earnings",
                        "earnings move", "percent move", "pct move", "ernmv",
                        "next earnings", "earnings reaction", "event effect",
                        "earnings date")),
    ("options_vol", ("implied vol", "implied", "option", "open interest",
                     "skew", "straddle", "volatilit", "vega", "atm",
                     "term structure")),
    ("analyst", ("estimate", "consensus", "guidance", "eps", "ebitda",
                 "revenue", "earnings per share", "forecast", "recommendation",
                 "target price", "revision", "analyst")),
    ("sentiment", ("sentiment", "news", "social", "buzz", "mood", "tone")),
    ("price_volume", ("price", "volume", "return", "vwap", "turnover")),
]
_FIELD_FAMILY_MAP = None


def _expr_field_tokens(expr):
    """Bare identifier tokens in an expression (split on non-identifier chars),
    so a wrapped field like vec_avg(best_fit_implied_announcement_effect) still
    exposes its inner field id for lookup."""
    out, cur = [], []
    for ch in (expr or ""):
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _family_from_text(text):
    t = (text or "").lower()
    for fam, kws in _FAMILY_KEYWORDS:
        if any(k in t for k in kws):
            return fam
    return None


def _load_field_family_map():
    """id -> family map from data_fields.json, keyed on id + description
    keywords. Cached; empty (stem-only fallback) when the catalog is missing."""
    global _FIELD_FAMILY_MAP
    if _FIELD_FAMILY_MAP is not None:
        return _FIELD_FAMILY_MAP
    mapping = {}
    path = Path(FIELD_CATALOG_PATH)
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                fid = r.get("id")
                if not fid:
                    continue
                blob = str(fid).replace("_", " ") + " " + str(r.get("description") or "")
                fam = _family_from_text(blob)
                if fam:
                    mapping[fid] = fam
    _FIELD_FAMILY_MAP = mapping
    return mapping


def field_family(field_expr):
    """Resolve a field id/expression to an affinity family. Tries the live
    harvested-catalog id->family map FIRST (robust to descriptive ids), then
    falls back to the hardcoded stem lists (shared with the decay / harvester
    families). Returns None when nothing matches, treated as neutral (never
    penalized)."""
    e = (field_expr or "").lower()
    # 1) Robust: route by any live field id present in the expression.
    fam_map = _load_field_family_map()
    if fam_map:
        for tok in _expr_field_tokens(field_expr):
            fam = fam_map.get(tok)
            if fam:
                return fam
    # 2) Stem fallback. Resolve earnings step/event fields BEFORE the options_vol
    # catch-all so the per-event move + event-timing fields get the change-operator
    # affinity the doc prescribes. Exclude the slow normalisers (absavgernmv /
    # ernmvstdev), which are denominators, not event signals.
    if (any(s in e for s in FAMILY_EARNINGS_EVENT_STEMS)
            and "ernmvstdev" not in e and "absavgernmv" not in e):
        return "earnings_event"
    if any(s in e for s in FAMILY_OPTIONS_STEMS):
        return "options_vol"
    if any(s in e for s in FAMILY_ANALYST_STEMS):
        return "analyst"
    if any(s in e for s in FAMILY_SENTIMENT_STEMS):
        return "sentiment"
    if any(s in e for s in FAMILY_PRICE_VOLUME_STEMS):
        return "price_volume"
    return None


def operator_affinity_weight(operator_name, family):
    """Soft sampling weight for applying `operator_name` to a field of `family`:
    AFFINITY_PREFERRED_WEIGHT if preferred, AFFINITY_DISCOURAGED_WEIGHT if
    discouraged, else 1.0. Returns 1.0 when affinity is disabled or the family is
    unknown, so callers never need to special-case it."""
    if not AFFINITY_ENABLED or not family:
        return 1.0
    policy = OPERATOR_AFFINITY.get(family)
    if not policy:
        return 1.0
    op = (operator_name or "").lower()
    if op in {o.lower() for o in policy.get("prefer", [])}:
        return AFFINITY_PREFERRED_WEIGHT
    if op in {o.lower() for o in policy.get("avoid", [])}:
        return AFFINITY_DISCOURAGED_WEIGHT
    return 1.0


# --- Hard guards (the ONLY forbidden combinations) --------------------------
# Soft affinity above never forbids anything. A tiny, CERTAIN set of combos is,
# however, genuinely meaningless and is hard-blocked at validation time so no
# simulation is ever wasted on it. Keep this list small and beyond doubt.
AFFINITY_HARD_GUARD_ENABLED = os.getenv("WQ_AFFINITY_HARD_GUARD", "1").strip().lower() in ("1", "true", "yes", "on")
# First-difference / change operators. Applied to a ROLLING-TENOR field -- one
# whose tenor label rolls forward every period (the m2/m3/m4 ATM-IV chain, the
# front-month strike / days-to-expiry) -- a delta measures the tenor ROLL, not a
# real change in the underlying: a fake monthly jump. ts_delta stays VALID on
# true step/event fields (earnings counts, next-earnings date), so the ban is
# keyed to the rolling-chain stems ONLY, never to the operator alone.
DELTA_LIKE_OPERATORS = ["ts_delta", "ts_av_diff", "delta"]
ROLLING_TENOR_STEMS = ["m2atmiv", "m3atmiv", "m4atmiv", "m1lostrike",
                       "m2lostrike", "m1dtex", "m2dtex"]

# --- Crowded / arbitraged-away signal zoo (ANTI-TARGET, never seeds) --------
# Canonical public-style structures whose literal forms are heavily crowded
# (the correct use of the 2015 "101 Formulaic Alphas": as an anti-target, not a
# seed source). The originality penalty discourages re-deriving these. Written
# with real fields so AST-motif extraction maps them to the right data groups.
CROWDED_ALPHA_ZOO = [
    "group_neutralize(-ts_delta(close, 5), MARKET)",
    "group_neutralize(-ts_zscore(returns, 5), MARKET)",
    "group_neutralize(-rank(ts_corr(close, volume, 10)), MARKET)",
    "group_neutralize(-(close - vwap), MARKET)",
    "group_neutralize(ts_rank(ts_delta(close, 20), 20), MARKET)",
    "group_neutralize(rank(ts_std_dev(returns, 20)), MARKET)",
]

# --- Network behaviour -------------------------------------------------------
BROWSER_IMPERSONATE = "chrome120"
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
# WorldQuant throttles the /simulations endpoint hard. Keep concurrency
# conservative -- too many in-flight POSTs trigger sustained 429s that stall
# the whole run. Raise only if you have a higher consultant concurrency quota.
MAX_CONCURRENT_SIMULATIONS = 3
# Polling a single simulation: total budget and interval between polls.
SIMULATION_POLL_TIMEOUT_SECS = 600
SIMULATION_POLL_INTERVAL_SECS = 2.0
# Retries for genuine transport/5xx errors. 429 throttling and auth refreshes
# are handled separately and do NOT consume this budget.
NETWORK_MAX_ERROR_RETRIES = 5
# Ceiling for the exponential 429 backoff. On sustained throttling the network
# engine escalates the wait (6s -> 12s -> 24s ...) up to this cap instead of
# hammering a flat 6s interval, letting the server-side simulation queue drain.
THROTTLE_MAX_BACKOFF_SECS = 120
# Bounded wait (seconds) for a fresh cookie if programmatic auth is unavailable.
AUTH_REFRESH_MAX_WAIT_SECS = 600
# Max consecutive auth refreshes per request before giving up. Guards against an
# endless 401 -> refresh -> 401 loop when a "successful" login keeps yielding a
# cookie that the API still rejects.
AUTH_MAX_REFRESH_ATTEMPTS = 3
# Programmatic-login rate limiting (runaway sign-in guard). WorldQuant locks an
# account after a burst of sign-ins (observed ~25/day). Previously _authenticate()
# had NO cooldown, so a session that logs in "successfully" but is still rejected
# by the API (the Persona / face-ID step-up case) drove an unbounded
# login -> still-401 -> login loop that tripped the lockout overnight. These knobs
# HARD-bound programmatic logins: a minimum spacing between attempts and a rolling
# cap kept well under the platform lockout. When the cap is hit the engine trips a
# circuit breaker and falls back to the human pause-and-resume (paste a fresh
# WQ_COOKIE) path instead of hammering /authentication. Set
# WQ_AUTH_MAX_LOGINS_PER_WINDOW=0 to disable programmatic login entirely (cookie-only).
AUTH_MIN_LOGIN_INTERVAL_SECS = float(os.getenv("WQ_AUTH_MIN_LOGIN_INTERVAL_SECS", "900"))
AUTH_LOGIN_WINDOW_SECS = float(os.getenv("WQ_AUTH_LOGIN_WINDOW_SECS", str(24 * 3600)))
AUTH_MAX_LOGINS_PER_WINDOW = int(os.getenv("WQ_AUTH_MAX_LOGINS_PER_WINDOW", "10"))
# Self-correlation check retries (A2). The realized self-correlation gate FAILS
# CLOSED: if every attempt to fetch /correlations/self errors out, the alpha is
# treated as fully correlated (max-corr 1.0) and withheld from promotion rather
# than being waved through as "decorrelated". Retrying a few times keeps a
# transient blip from permanently sidelining a genuinely good alpha.
CORRELATION_CHECK_ATTEMPTS = int(os.getenv("WQ_CORRELATION_CHECK_ATTEMPTS", "3"))

# --- Session resilience (overnight runs) ------------------------------------
# WorldQuant logs sessions out periodically and the Persona / face-ID
# re-verification is HUMAN-ONLY -- it cannot be bypassed programmatically. These
# knobs instead let a run SURVIVE a logout: persist the session across restarts,
# keep it warm, and pause-then-resume around a forced re-auth instead of
# crashing and losing progress.
# Where the live session cookie (and its parsed expiry) is cached between runs.
SESSION_CACHE_PATH = os.getenv("WQ_SESSION_CACHE", ".wq_session.json")
# Proactively refresh the cookie once it is within this many seconds of expiry.
COOKIE_REFRESH_MARGIN_SECS = 600
# Keep-alive heartbeat: a lightweight authenticated ping that prevents IDLE
# session timeouts between simulations. It cannot defeat the hard face-ID limit.
KEEPALIVE_ENABLED = True
KEEPALIVE_INTERVAL_SECS = 180
KEEPALIVE_ENDPOINT = "/authentication"
# When a forced re-auth needs the human (face-ID), the run PAUSES and waits up
# to this long for a fresh session -- via auto-login, an updated WQ_COOKIE in
# .env, or the cached session file -- before giving up. 8h covers an overnight
# gap so the generator resumes itself when you log back in.
AUTH_PAUSE_MAX_WAIT_SECS = 8 * 3600
# Sentinel file written while human re-auth is pending, so an external watcher
# (a shell script, a phone shortcut, etc.) can notice and alert you.
REAUTH_FLAG_PATH = os.getenv("WQ_REAUTH_FLAG", ".wq_reauth_needed")
# Run-level checkpoint (next generation index + counters) for a clean resume.
CHECKPOINT_PATH = os.getenv("WQ_CHECKPOINT", ".wq_checkpoint.json")

# --- Genetic algorithm parameters -------------------------------------------
POPULATION_SIZE = 200
GENERATIONS = 500
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.45
TOURNAMENT_SIZE = 7
PARSIMONY_COEFFICIENT = 0.002
EXPERIENCE_RESEED_INTERVAL = int(os.getenv("WQ_EXPERIENCE_RESEED_INTERVAL", "5"))
# Bumped 4 -> 16: each periodic reseed injects a larger batch of FRESH
# breadth-first seeds (drawn across the whole field universe via the experience-
# memory-steered grammar engine), so diversity is continually RE-injected to
# counter selection collapsing the population onto one field family between
# reseeds. Still a small fraction of POPULATION_SIZE, so the extra per-reseed
# simulation cost is negligible.
EXPERIENCE_RESEED_COUNT = int(os.getenv("WQ_EXPERIENCE_RESEED_COUNT", "16"))
# Turnover-control mutation: let the genetic engine wrap a signal in a
# trade_when / keep gate (the WorldQuant turnover levers) so high-turnover
# alphas can be throttled toward the fitness bar. Only operators present in the
# live operator set are used; set False to disable.
TURNOVER_GATE_MUTATION_ENABLED = True

# --- Experience memory (failure-feedback steering) --------------------------
# Recently-failed expressions + WHY they failed are fed back into seed
# generation so the grammar engine (and the optional LLM) actively avoid
# known-bad structures and over-represented fields. This is the "Critic's
# Memory": it prevents re-deriving the same losers and keeps the pool diverse.
EXPERIENCE_MEMORY_ENABLED = True
EXPERIENCE_MEMORY_SIZE = 200            # most-recent failures retained for feedback
EXPERIENCE_MAX_BANNED_FIELDS = 4        # cap on how many fields get down-weighted
EXPERIENCE_BANNED_FIELD_PENALTY = 0.6   # selection weight for a discouraged field (1.0 = neutral)

# --- Inline refinement (local hill-climb on promoted winners) ---------------
# When a simulated alpha clears the promotion gates, branch it locally to push
# its stats further. Tiers escalate settings -> windows -> operator wraps; the
# loop stops at REFINE_MAX_BRANCHES (hard cap) or when the most aggressive tier
# stops improving (plateau). Every branch is a real simulation and counts toward
# the Deflated-Sharpe trial penalty, so refinement can't curve-fit past the
# deflation guard.
REFINEMENT_ENABLED = True
REFINE_MAX_BRANCHES = 24      # hard cap on total branches per promoted alpha
REFINE_BATCH_SIZE = 8         # branches simulated per round
REFINE_PATIENCE = 1           # no-improvement rounds before escalating a tier
REFINE_MIN_IMPROVEMENT = 0.01 # min deflated-fitness gain that counts as better
# Refine TRIGGER threshold, decoupled from the MIN_SHARPE submit gate. Alphas
# at/above this Sharpe but still below MIN_SHARPE are "near-winners": the
# dimension-targeted hill-climb actively branches them toward submittable
# instead of waiting for something to first cross MIN_SHARPE on its own (the old
# chicken-and-egg, since refinement used to fire only on PROMOTED winners). Set
# equal to MIN_SHARPE to restore the old winners-only behaviour. The submit gate
# is unchanged -- near-winners are never marked qualified or submitted.
REFINE_SHARPE_THRESHOLD = float(os.getenv("WQ_REFINE_SHARPE_THRESHOLD", "1.00"))
# Hard cap on how many NEAR-WINNERS (beyond promoted winners) are refined per
# generation, highest-fitness first, so opening the trigger can't flood the
# 429-throttled /simulations queue. Promoted winners are always refined; -1
# removes the cap.
REFINE_MAX_TARGETS_PER_GEN = int(os.getenv("WQ_REFINE_MAX_TARGETS_PER_GEN", "6"))
# One-time startup refinement of RESUMED winners. Alphas loaded from the
# database on resume go straight into the population and BYPASS
# _evaluate_population, so -- unlike freshly-evaluated candidates -- they never
# trigger inline refinement; a strong 1.0+ resumed alpha would otherwise only
# ever act as a crossover/mutation parent. When enabled, the top resumed
# winners / near-winners (Sharpe >= REFINE_SHARPE_THRESHOLD) are hill-climbed
# ONCE, immediately after resume, so an existing strong cluster keeps improving
# from generation 0. Highest-fitness-first and bounded so it can't flood the
# 429-throttled /simulations queue. Set STARTUP_REFINE_ENABLED=0 (or MAX=0) to
# skip it; MAX=-1 removes the cap.
STARTUP_REFINE_ENABLED = os.getenv("WQ_STARTUP_REFINE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
STARTUP_REFINE_MAX_TARGETS = int(os.getenv("WQ_STARTUP_REFINE_MAX_TARGETS", "6"))

# --- Sign-flip (negation) harvest -------------------------------------------
# A strongly NEGATIVE-Sharpe alpha is a correct signal pointing the WRONG way:
# negating it (multiply the signal by -1) flips Sharpe, returns AND WorldQuant
# fitness sign while leaving turnover UNCHANGED -- so Sharpe -1.30 / fitness
# -1.05 becomes an instantly-submittable Sharpe +1.30 / fitness +1.05. Without
# this the engine throws those away as losers, discarding ~half the search.
# After a generation is scored, every freshly-evaluated alpha whose MIRROR is at
# least refine-worthy (mirror Sharpe >= REFINE_SHARPE_THRESHOLD) is re-submitted
# as group_neutralize(-signal, GROUP): a fully-qualifying mirror is promoted, and
# a near-winner mirror (mirror Sharpe in [REFINE_SHARPE_THRESHOLD, MIN_SHARPE))
# is then hill-climbed toward submittable -- so we also capture flips that aren't
# winners YET but can be refined into one. The mirror is a genuinely distinct
# expression and MUST be simulated to earn a real, submittable alpha_id -- its
# metrics can't simply be synthesized from the original's.
NEGATION_ENABLED = os.getenv("WQ_NEGATION_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
# Hard cap on mirrors simulated per generation (highest mirror-Sharpe first) so
# the harvest can't flood the 429-throttled /simulations queue. -1 removes it.
NEGATION_MAX_PER_GEN = int(os.getenv("WQ_NEGATION_MAX_PER_GEN", "8"))
# One-time STARTUP negation harvest over RESUMED alphas (B6). The per-generation
# harvest above only fires on freshly-evaluated candidates, so strongly-negative
# alphas already in the database (loaded straight into the population on resume)
# would never be mirrored. When enabled, every resumed alpha whose mirror is at
# least refine-worthy is flipped ONCE, immediately after resume, turning the
# largest ready-made pool of losers into positive candidates. Bounded by
# NEGATION_RESUME_MAX (falls back to NEGATION_MAX_PER_GEN). Set
# NEGATION_RESUME_ENABLED=0 to skip (e.g. if you are injecting negatives by hand).
NEGATION_RESUME_ENABLED = os.getenv("WQ_NEGATION_RESUME_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
NEGATION_RESUME_MAX = int(os.getenv("WQ_NEGATION_RESUME_MAX", "12"))

# --- Deflation / statistics --------------------------------------------------
PERIODS_IN_YEAR = 252
# WorldQuant (like scipy.stats.kurtosis) reports EXCESS kurtosis (normal == 0).
# The Deflated-Sharpe variance formula needs the full fourth moment (normal ==
# 3), so oos_deflation converts when this is True. Set False only if your data
# source reports non-excess kurtosis.
KURTOSIS_IS_EXCESS = True
# Conservative default IS track-record length (~1 trading year) when the API
# does not report one. A SMALL default keeps the Deflated Sharpe honest, since
# a large track record artificially shrinks the standard error.
DEFAULT_TRACK_RECORD_LENGTH = 252
# Cap on the effective multiple-testing trial count fed into the Deflated Sharpe
# (A3). The raw count of completed simulations grows every generation, which
# would push the expected-max-Sharpe hurdle up without bound and crush late-run
# deflated fitness toward 0 (penalizing alphas for the engine running longer,
# not for being worse). Capping keeps deflation stable. <=1 disables the cap.
DEFLATION_MAX_TRIALS = int(os.getenv("WQ_DEFLATION_MAX_TRIALS", "1000"))

# --- Promotion / submission gating ------------------------------------------
MIN_SHARPE = 1.25
MAX_TURNOVER = 0.70
# Hard submittable turnover FLOOR. WorldQuant BRAIN REJECTS any submission whose
# turnover is below ~1%, so an alpha under this floor can never be marked
# qualified (orchestrator gate) and is screened out at the submission query too.
# This is a HARD gate, not a preference.
MIN_TURNOVER = float(os.getenv("WQ_MIN_TURNOVER", "0.01"))
# Soft turnover TARGET-BAND floor. Below this the engine stops rewarding "lower
# is always better": NSGA-II clamps the turnover objective here (no more credit
# for the race to zero) and dimension-targeted refinement treats too-low turnover
# as an UNHEALTHY axis and actively trades it UP for Sharpe (shorter windows /
# lower decay / un-gating). Genuinely good low-turnover winners are NOT discarded
# -- this only removes the race-to-zero incentive and breaks the slow-data,
# self-correlated monoculture. Raise toward 0.10 to push harder. Keep between
# MIN_TURNOVER and MAX_TURNOVER.
TURNOVER_TARGET_LOW = float(os.getenv("WQ_TURNOVER_TARGET_LOW", "0.05"))
MAX_SELF_CORRELATION = 0.70
# BRAIN submittability-checks gate. BRAIN's /alphas/{id} response carries an
# is.checks array (PASS / FAIL / PENDING per gate: concentration, sub-universe
# Sharpe, turnover floor, fitness, ...). A FAIL means BRAIN ITSELF would reject
# the alpha -- including the concentration / sub-universe failures our own metric
# thresholds never see. When enabled, an alpha with ANY failed is.check can never
# be marked qualified (and is screened at submission), so the engine stops
# promoting alphas BRAIN considers un-submittable. PENDING submission-time checks
# (e.g. self-correlation) are NOT failures and never block. Fails OPEN when the
# platform returns no checks. Set 0 to disable.
CHECKS_GATE_ENABLED = os.getenv("WQ_CHECKS_GATE", "1").strip().lower() in ("1", "true", "yes", "on")
# Risk gates (C9). BRAIN will not accept an alpha with a runaway max drawdown or
# a non-positive margin, so promoting one just wastes a capped submission slot on
# something un-submittable. These are checked at promotion time (in addition to
# Sharpe / turnover / fitness / self-correlation). Thresholds are deliberately
# GENEROUS so they only catch genuinely broken alphas; a metric that the platform
# does not report defaults to 0.0 and therefore PASSES. Set
# DRAWDOWN_MARGIN_GATE_ENABLED=0 to turn the checks off.
DRAWDOWN_MARGIN_GATE_ENABLED = os.getenv("WQ_DRAWDOWN_MARGIN_GATE", "1").strip().lower() in ("1", "true", "yes", "on")
# Max acceptable IS max drawdown as a fraction (0.70 == 70%). Set very large
# (e.g. 1e9), or DRAWDOWN_MARGIN_GATE_ENABLED=0, to disable.
MAX_DRAWDOWN = float(os.getenv("WQ_MAX_DRAWDOWN", "0.70"))
# Minimum acceptable IS margin (profit per $ traded). BRAIN expresses margin in
# small decimals; 0.0 simply requires a non-negative margin. Lower (e.g. -1.0)
# to effectively disable.
MIN_MARGIN = float(os.getenv("WQ_MIN_MARGIN", "0.0"))
# Structural near-duplicate threshold. This is a CHEAP STRING proxy used only to
# avoid wasting simulations on near-identical losers; it is NOT a claim of
# return-decorrelation. Realized self-correlation (via the WorldQuant
# /correlations/self endpoint) is what actually gates promotion & submission.
NEAR_DUPLICATE_SIMILARITY = 0.97
# Hard cap on how many alphas submit_to_worldquant.py will push in one run.
MAX_SUBMISSIONS_PER_RUN = 10

# --- PnL-based decorrelation submission selector ----------------------------
# WorldQuant endpoint that returns an alpha's daily PnL recordset. Parsed
# DEFENSIVELY (list-of-[date, value] OR list-of-dicts), so a minor schema
# difference degrades to "no PnL" instead of crashing. Adjust if your tenant
# exposes a different path (e.g. /recordsets/daily-pnl).
WQ_PNL_ENDPOINT_TEMPLATE = os.getenv("WQ_PNL_ENDPOINT", "/alphas/{alpha_id}/recordsets/pnl")
# Soft correlation budget: a candidate is preferred while its max |PnL corr|
# with the already-selected basket stays at/under SOFT. HARD is WorldQuant's
# rejection ceiling (== MAX_SELF_CORRELATION) used only to backfill spare slots.
SUBMISSION_CORR_SOFT = float(os.getenv("WQ_SUBMISSION_CORR_SOFT", "0.50"))
SUBMISSION_CORR_HARD = float(os.getenv("WQ_SUBMISSION_CORR_HARD", "0.70"))
# Minimum overlapping trading days before a pairwise correlation is trusted.
SUBMISSION_CORR_MIN_OVERLAP = int(os.getenv("WQ_SUBMISSION_CORR_MIN_OVERLAP", "30"))
# Order/filter submissions with the PnL selector when stored PnL is available.
# Falls back to the existing AST-similarity _diversified_order when PnL is
# missing, so enabling it can NEVER break current behaviour.
SUBMISSION_USE_PNL_SELECTOR = os.getenv("WQ_SUBMISSION_USE_PNL_SELECTOR", "1").strip().lower() in ("1", "true", "yes", "on")

# --- Return-orthogonality SELECTION (run_4 decorrelation lever) --------------
# Option B / the run_4 experiment. The GA's structural orthogonality shaping
# (oos_deflation.calculate_orthogonal_fitness_batch) only penalizes SYNTACTIC
# similarity, so the search bred structurally-novel alphas that still tracked ONE
# return stream (the ENB collapse). When enabled, _simulate_alpha fetches each
# strong alpha's daily PnL and _evaluate_population damps its fitness by the max
# |PnL correlation| to the current elite basket -- so NSGA-II breeds toward
# RETURN-orthogonal alphas, directly targeting effective bet count. OFF by
# default (byte-for-byte the prior behaviour); set WQ_RETURN_DECORR_SELECTION=1
# for run_4. EXPECT headline Sharpe/fitness to FALL as the population spreads off
# the dominant factor -- judge run_4 on ENB / effective family count / PBO, NOT
# on max fitness.
RETURN_DECORR_SELECTION_ENABLED = os.getenv("WQ_RETURN_DECORR_SELECTION", "0").strip().lower() in ("1", "true", "yes", "on")
# Penalty steepness: multiplier = exp(-K * corr^2) on the (positive) adjusted
# DSR. Higher K punishes return-correlation harder.
RETURN_DECORR_K = float(os.getenv("WQ_RETURN_DECORR_K", "2.5"))
# Minimum overlapping trading days before a pairwise PnL correlation is trusted
# (mirrors the submission selector's SUBMISSION_CORR_MIN_OVERLAP).
RETURN_DECORR_MIN_OVERLAP = int(os.getenv("WQ_RETURN_DECORR_MIN_OVERLAP", "60"))
# Only fetch PnL (and apply the penalty) for alphas at/above this Sharpe -- the
# only ones that realistically become elites/parents -- so the extra PnL GETs
# stay bounded on the 429-throttled queue. Keep aligned with
# REFINE_SHARPE_THRESHOLD.
RETURN_DECORR_MIN_SHARPE = float(os.getenv("WQ_RETURN_DECORR_MIN_SHARPE", "1.00"))
# Poll budget for the async PnL recordset (200 + empty body + Retry-After until
# the rows are generated), mirroring backfill_pnl.PNL_POLL_MAX_ATTEMPTS.
PNL_FETCH_MAX_ATTEMPTS = int(os.getenv("WQ_PNL_FETCH_MAX_ATTEMPTS", "8"))

# --- Surrogate pre-screener (SHADOW MODE ONLY by default) -------------------
# A cheap model that PREDICTS whether a candidate is worth simulating. OFF the
# hot path by default: SHADOW only LOGS what it WOULD skip and never blocks a
# simulation, so it cannot starve the generator. Promote to a soft prioritizer
# ONLY after evaluate_prescreener.py shows an acceptable false-negative rate.
SURROGATE_ENABLED = os.getenv("WQ_SURROGATE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
SURROGATE_SHADOW_ONLY = os.getenv("WQ_SURROGATE_SHADOW_ONLY", "1").strip().lower() in ("1", "true", "yes", "on")
SURROGATE_MODEL_PATH = os.getenv("WQ_SURROGATE_MODEL", str(Path(__file__).with_name("surrogate_model.pkl")))
# Label: a row is a "winner" if it cleared this Sharpe AND sits in the turnover
# band. Keep aligned with the promotion gate.
SURROGATE_WINNER_SHARPE = float(os.getenv("WQ_SURROGATE_WINNER_SHARPE", "1.25"))
# Probability below which SHADOW mode would (only logs!) consider skipping a sim.
SURROGATE_SKIP_THRESHOLD = float(os.getenv("WQ_SURROGATE_SKIP_THRESHOLD", "0.10"))

# WorldQuant FITNESS gate (Upgrade #1). BRAIN's headline score is
# Fitness = sqrt(abs(Returns) / max(turnover, 0.125)) * Sharpe, and the
# documented submission bar is Fitness >= 1.0 / Sharpe >= 1.25 for delay-1
# (stricter for delay-0). A high-Sharpe but high-turnover alpha can still fail
# the fitness bar, so we gate on it EXPLICITLY in addition to Sharpe/turnover.
MIN_FITNESS = 1.0          # delay-1 submission floor
MIN_FITNESS_DELAY0 = 1.3   # stricter delay-0 floor (used when DEFAULT_DELAY == 0)

# --- Frequent Subtree Avoidance (Upgrade #3, success-side diversity) --------
# Mine the most common structural motifs among CURRENT WINNERS and steer seeding
# + mutation away from them so the pool does not collapse onto one shape. The
# success-side complement to the failure-feedback experience memory.
FSA_ENABLED = True
FSA_TOP_K = 3              # number of most-frequent winner motifs to discourage
FSA_MIN_WINNERS = 10       # don't start avoiding motifs until this many winners exist
FSA_PENALTY = 0.35         # keep-probability for a candidate carrying an avoided motif

# --- Structural monoculture cap (selection-time diversity) ------------------
# Independent of FSA above (which only engages once FSA_MIN_WINNERS winners
# exist -- useless on a run with zero submittable alphas): after each NSGA-II
# sort, no single structural SKELETON (the alpha shape with fields / constants /
# neutralization group ignored, e.g. group_neutralize(rank(_))) may occupy more
# than this fraction of the surviving POPULATION_SIZE. Over-represented members
# are pushed to the tail and fall off truncation first, so diverse shapes are
# guaranteed room to breed even before anything qualifies. 1.0 disables the cap.
SKELETON_MAX_FRACTION = float(os.getenv("WQ_SKELETON_MAX_FRACTION", "0.35"))

# --- Structural FIELD-diversity cap (selection-time, monoculture breaker) ----
# The skeleton cap above bounds shape monoculture but is BLIND to fields:
# group_neutralize(rank(iv_a),_) and group_neutralize(rank(iv_b),_) share the
# skeleton group_neutralize(rank(_),_), so a population can satisfy the skeleton
# cap while still collapsing onto two volatility fields (exactly the observed
# gen-2/3 monoculture). After each NSGA-II sort, cap how many surviving members
# may share the SAME dominant data field; overflow is pushed to the tail so it
# falls off the [:POPULATION_SIZE] truncation first. This preserves field
# breadth THROUGH selection (not just at gen-0 seeding), so a couple of
# high-fitness fields can't crowd the whole pool and breed a correlated
# offspring family. 1.0 = off.
FIELD_DIVERSITY_MAX_FRACTION = float(os.getenv("WQ_FIELD_DIVERSITY_MAX_FRACTION", "0.30"))

# --- Originality vs a "crowded" alpha zoo (Upgrade #4) -----------------------
# Soft penalty (NOT a hard reject, to avoid nuking our own generic archetypes)
# applied to candidates whose structure is too close to well-known / arbitraged
# public signals. Similarity is AST-motif Jaccard.
ORIGINALITY_ENABLED = True
ORIGINALITY_PENALTY_SIMILARITY = 0.85  # motif-Jaccard above which the penalty bites
ORIGINALITY_PENALTY = 0.5              # fitness multiplier when too close to the zoo
# AST-motif similarity above which a NEW candidate is treated as a structural
# duplicate of a known loser and skipped (replaces the old char-ngram proxy).
AST_DEDUP_SIMILARITY = 0.92

# --- Overfitting-risk shaping (Upgrade #6, IS vs OOS) -----------------------
# When the platform reports an out-of-sample Sharpe, demote alphas whose IS-OOS
# gap is wide (the textbook over-fit signature). Neutral (1.0) when no OOS
# figure is available. A simplified CSCV-style PBO is logged per generation.
OVERFIT_RISK_ENABLED = True
OVERFIT_RISK_K = 1.5       # steepness of the IS-OOS gap penalty
PBO_DIAGNOSTIC_ENABLED = True

# --- Submission diversification (Upgrade #7) --------------------------------
# BRAIN rewards uncorrelated baskets and penalizes concentration. Cap the share
# of any single data category in one run and prefer marginally decorrelated
# alphas (greedy max-marginal-contribution by AST-motif distance).
SUBMISSION_MAX_CATEGORY_FRACTION = 0.30  # <=30% of a run from one data category
SUBMISSION_MAX_SIMILARITY = 0.90         # skip a candidate too similar to one already picked
SUBMISSION_MIN_DELAY0_FRACTION = 0.05    # informational: BRAIN wants >=5% delay-0

# --- Dimension-targeted refinement (Upgrade #5) -----------------------------
# Temperature for the softmax that picks WHICH weak dimension (Sharpe, turnover,
# correlation) a refinement round attacks. Lower => greedier toward the single
# weakest axis; higher => more exploratory across axes.
REFINE_TEMPERATURE = 1.0

# --- Simulation settings -----------------------------------------------------
DEFAULT_INSTRUMENT = "EQUITY"
DEFAULT_REGION = "USA"
DEFAULT_DELAY = 1
DEFAULT_TRUNCATION = 0.08
# The expression always carries its own group_neutralize(...); platform-side
# neutralization is therefore disabled to avoid double neutralization. This is
# the single source of truth used by every payload builder in the project.
SETTINGS_NEUTRALIZATION = "NONE"

NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"]
# Neutralization sampling weights (sparse-data concentration fix). On sparse /
# event datasets (earnings, options) the FINE-grained groups (SUBINDUSTRY,
# INDUSTRY) hold only a handful of LIVE names per bucket, so
# group_neutralize(..., SUBINDUSTRY) demeans 2-3 names against each other and
# manufactures the "weight too strongly concentrated / too few instruments"
# failure. The COARSE groups (SECTOR, MARKET) demean against a much larger live
# cross-section and spread weight evenly. These weights BIAS the random
# {NEUTRALIZATION} choice toward the coarse groups while still EXPLORING the fine
# ones (nothing removed). Set all to 1.0 (or WQ_NEUT_W_*=1) to restore uniform.
NEUTRALIZATION_WEIGHTS = {
    "SUBINDUSTRY": float(os.getenv("WQ_NEUT_W_SUBINDUSTRY", "0.5")),
    "INDUSTRY": float(os.getenv("WQ_NEUT_W_INDUSTRY", "0.8")),
    "SECTOR": float(os.getenv("WQ_NEUT_W_SECTOR", "1.6")),
    "MARKET": float(os.getenv("WQ_NEUT_W_MARKET", "1.4")),
}


def choose_neutralization():
    """Weighted-random neutralization group (NEUTRALIZATION_WEIGHTS): biased
    toward the coarser SECTOR / MARKET groups that avoid sparse-bucket weight
    concentration, while still exploring SUBINDUSTRY / INDUSTRY. Falls back to a
    uniform choice when the weights vanish, so callers never special-case it."""
    weights = [max(0.0, NEUTRALIZATION_WEIGHTS.get(n, 1.0)) for n in NEUTRALIZATIONS]
    if sum(weights) <= 0:
        return random.choice(NEUTRALIZATIONS)
    return random.choices(NEUTRALIZATIONS, weights=weights, k=1)[0]


# --- Neutralization-OPERATOR diversity (break the group_neutralize monoculture)
# Every template hardcodes group_neutralize(signal, GROUP) as the outer wrap, and
# operator mutation only swaps WITHIN an operator category -- group_neutralize is
# category "Group", so the search can never reach the other neutralizers even
# though they exist in the catalog. These knobs let the genetic engine RE-WRAP a
# signal's outer neutralization into a different style (see
# GeneticEngine._mutate_neutralization).
#
# OFF BY DEFAULT (opt-in). group_neutralize is the robust, proven workhorse on
# this engine and -- crucially -- SETTINGS_NEUTRALIZATION is "NONE", so the
# IN-EXPRESSION neutralizer is the ONLY neutralization an alpha gets. Swapping it
# changes an alpha's whole risk profile, so most swaps land OUTSIDE the tuned
# group/turnover regime and fail the IS gates; with a throttled simulation
# budget that is mostly wasted quota. The MONOCULTURE is already cured by the
# selection-time FIELD_DIVERSITY cap (pure reordering, zero alpha-quality risk)
# plus the inner-signal-diverse seed templates and the periodic reseed -- all of
# which KEEP group_neutralize. Enable this only to deliberately EXPLORE
# decorrelation when you have spare budget. Set WQ_NEUT_MUTATION=1 to turn on.
NEUTRALIZATION_MUTATION_ENABLED = os.getenv("WQ_NEUT_MUTATION", "0").strip().lower() in ("1", "true", "yes", "on")
# Candidate outer-neutralization STYLES the mutation may pick WHEN enabled. The
# default set is deliberately GROUP-PRESERVING -- group_zscore / group_rank keep
# the exact same within-group neutralization as group_neutralize and only change
# the within-group transform, so they add structural variety WITHOUT stripping
# the neutralization that makes alphas pass IS. The market-wide neutralizers
# (normalize / zscore) and the orthogonalizer (vector_neut) are NOT in the
# default because under neutralization=NONE they drop the group structure /
# change the risk profile; add them via WQ_NEUT_STYLES only when experimenting.
# Every style MUST be in operators.json or it is filtered out at startup. NOTE:
# group_vector_neut (the ideal lever) is NOT in our operators.json yet -- add it
# via probe_wq before listing it here, or it will be dropped.
NEUTRALIZATION_STYLES = [s.strip() for s in os.getenv(
    "WQ_NEUT_STYLES",
    "group_neutralize,group_zscore,group_rank",
).split(",") if s.strip()]
# Universe funnel. The GA explores on ONE consistent, liquid universe
# (TOP3000 -- deepest history, least small-cap noise, least overfit) so every
# candidate's Sharpe/turnover is directly comparable under NSGA-II and the
# per-period variance estimate behind the Deflated Sharpe is not polluted by
# mixing universes. The other universes are NOT searched directly; instead a
# PROMOTED winner is swept across them (see UNIVERSE_SWEEP_* below) as a
# robustness / diversification check. This also cuts the per-generation
# simulation count ~4x, which directly relieves the /simulations 429 throttling.
UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200"]
PRIMARY_UNIVERSE = os.getenv("WQ_PRIMARY_UNIVERSE", "TOP3000")
# Once an alpha clears the promotion gates on the primary universe, re-test it
# on every OTHER universe: this reveals where it is strongest and harvests
# submittable variants (the same expression on a different universe is a
# distinct, lightly-decorrelated submission). Only alphas at/above this Sharpe
# are swept, so the extra simulations are spent only on genuinely strong finds.
UNIVERSE_SWEEP_ENABLED = True
UNIVERSE_SWEEP_MIN_SHARPE = float(os.getenv("WQ_UNIVERSE_SWEEP_MIN_SHARPE", "1.5"))
DECAYS = [0, 5, 10, 15, 20]
# O(1) lookup for decay index (used in decorrelation refinement)
DECAY_TO_INDEX = {d: i for i, d in enumerate(DECAYS)}


def build_settings(universe, decay, neutralization=SETTINGS_NEUTRALIZATION):
    """Single source of truth for simulation settings (used everywhere)."""
    return {
        "instrumentType": DEFAULT_INSTRUMENT,
        "region": DEFAULT_REGION,
        "universe": universe,
        "delay": DEFAULT_DELAY,
        "decay": decay,
        "neutralization": neutralization,
        "truncation": DEFAULT_TRUNCATION,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False,
    }


def build_simulation_payload(expression, universe, decay):
    return {
        "type": "REGULAR",
        "settings": build_settings(universe, decay),
        "regular": expression,
    }


def worldquant_fitness(sharpe, returns, turnover):
    """Replicate BRAIN's headline fitness (Upgrade #1):
        Fitness = sqrt(|annualized returns| / max(turnover, 0.125)) * Sharpe.
    Returns 0.0 on missing/non-finite inputs so a missing-returns alpha is simply
    gated out instead of crashing the promotion path.
    """
    try:
        s = float(sharpe)
        r = float(returns)
        t = max(abs(float(turnover)), 0.125)
    except (TypeError, ValueError):
        return 0.0
    if not all(math.isfinite(x) for x in (s, r, t)):
        return 0.0
    return math.sqrt(abs(r) / t) * s


# --- Operator metadata (lazy-loaded, fails loudly) --------------------------
def _load_operator_metadata():
    operators_path = Path(__file__).with_name("operators.json")
    if not operators_path.exists():
        raise ConfigurationError(
            f"operators.json not found at {operators_path}. Run probe_wq.py once "
            "to download operator metadata before starting the factory."
        )
    try:
        with operators_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise ConfigurationError(f"Failed to parse operators.json: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ConfigurationError("operators.json is empty or malformed.")
    return data


def _split_signature_args(args_text: str) -> list[str]:
    if not args_text.strip():
        return []

    args = []
    current = []
    depth = 0
    quote = None
    left_smart_quote = chr(0x201C)
    right_smart_quote = chr(0x201D)
    for char in args_text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"', left_smart_quote, right_smart_quote):
            quote = right_smart_quote if char == left_smart_quote else char
            current.append(char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            arg = "".join(current).strip()
            if arg:
                args.append(arg)
            current = []
        else:
            current.append(char)

    arg = "".join(current).strip()
    if arg:
        args.append(arg)
    return args


def _extract_signature_args(definition: str) -> str | None:
    open_index = (definition or "").find("(")
    if open_index < 0:
        return None

    depth = 0
    for index, char in enumerate(definition[open_index:], start=open_index):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return definition[open_index + 1:index]
    return None


def _infer_operator_arity(definition: str) -> tuple[int, int | None]:
    args_text = _extract_signature_args(definition or "")
    if args_text is None:
        return 0, None

    args = _split_signature_args(args_text)
    if not args:
        return 0, 0

    variable = any("..." in arg or ".." in arg for arg in args)
    required = []
    for arg in args:
        if "..." in arg or ".." in arg:
            continue
        if "=" in arg:
            continue
        required.append(arg)

    min_args = len(required)
    max_args = None if variable else len(args)
    return min_args, max_args


_OPERATOR_CACHE: dict = {}
_OPERATOR_ATTRS = {
    "OPERATOR_METADATA",
    "ALLOWED_OPERATORS",
    "OPERATOR_CATEGORIES",
    "OPERATORS_BY_CATEGORY",
    "OPERATOR_ARITY",
    "TIME_SERIES_OPERATORS",
}


def _build_operator_tables() -> dict:
    metadata = _load_operator_metadata()
    categories = {}
    by_category = {}
    arity = {}
    for operator in metadata:
        name = operator.get("name")
        if not name:
            continue
        categories[name] = operator.get("category")
        by_category.setdefault(operator.get("category"), []).append(name)
        arity[name] = _infer_operator_arity(operator.get("definition", ""))
    allowed = sorted({op["name"] for op in metadata if "name" in op})
    if not allowed:
        raise ConfigurationError("No operators parsed from operators.json.")
    return {
        "OPERATOR_METADATA": metadata,
        "ALLOWED_OPERATORS": allowed,
        "OPERATOR_CATEGORIES": categories,
        "OPERATORS_BY_CATEGORY": by_category,
        "OPERATOR_ARITY": arity,
        "TIME_SERIES_OPERATORS": by_category.get("Time Series", []),
    }


def __getattr__(name):
    # PEP 562: lazily build operator tables on first access so importing config
    # never crashes (e.g. probe_wq.py must import config BEFORE operators.json
    # exists). Missing/empty metadata now raises loudly instead of silently
    # degrading to an empty operator set that fails every validation.
    if name in _OPERATOR_ATTRS:
        if not _OPERATOR_CACHE:
            _OPERATOR_CACHE.update(_build_operator_tables())
        return _OPERATOR_CACHE[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```