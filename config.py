import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)


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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_PROVIDER = "gemini"
# Override via the LLM_MODEL env var if Google renames/retires the model.
# "gemini-2.5-flash" is valid as of 2025+; older fallbacks: "gemini-2.0-flash",
# "gemini-1.5-flash".
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")

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
    "group_neutralize(ts_decay_linear(rank(ts_delta({SENTIMENT}, {LOOKBACK_SHORT})) * ts_zscore(-{VOLATILITY}, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})"
]

# --- Network behaviour -------------------------------------------------------
BROWSER_IMPERSONATE = "chrome120"
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5
# Polling a single simulation: total budget and interval between polls.
SIMULATION_POLL_TIMEOUT_SECS = 600
SIMULATION_POLL_INTERVAL_SECS = 2.0
# Retries for genuine transport/5xx errors. 429 throttling and auth refreshes
# are handled separately and do NOT consume this budget.
NETWORK_MAX_ERROR_RETRIES = 5
# Bounded wait (seconds) for a fresh cookie if programmatic auth is unavailable.
AUTH_REFRESH_MAX_WAIT_SECS = 600
# Max consecutive auth refreshes per request before giving up. Guards against an
# endless 401 -> refresh -> 401 loop when a "successful" login keeps yielding a
# cookie that the API still rejects.
AUTH_MAX_REFRESH_ATTEMPTS = 3

# --- Genetic algorithm parameters -------------------------------------------
POPULATION_SIZE = 200
GENERATIONS = 500
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.45
TOURNAMENT_SIZE = 7
PARSIMONY_COEFFICIENT = 0.002
EXPERIENCE_RESEED_INTERVAL = 5
EXPERIENCE_RESEED_COUNT = 4

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

# --- Promotion / submission gating ------------------------------------------
MIN_SHARPE = 1.25
MAX_TURNOVER = 0.70
MAX_SELF_CORRELATION = 0.70
# Structural near-duplicate threshold. This is a CHEAP STRING proxy used only to
# avoid wasting simulations on near-identical losers; it is NOT a claim of
# return-decorrelation. Realized self-correlation (via the WorldQuant
# /correlations/self endpoint) is what actually gates promotion & submission.
NEAR_DUPLICATE_SIMILARITY = 0.97
# Hard cap on how many alphas submit_to_worldquant.py will push in one run.
MAX_SUBMISSIONS_PER_RUN = 10

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
UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200"]
DECAYS = [0, 5, 10, 15, 20]


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