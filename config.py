import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
WQ_COOKIE = os.getenv("WQ_COOKIE", "")

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

BROWSER_IMPERSONATE = "chrome110"
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5

LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

POPULATION_SIZE = 200
GENERATIONS = 500
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.45
TOURNAMENT_SIZE = 7
PARSIMONY_COEFFICIENT = 0.002
EXPERIENCE_RESEED_INTERVAL = 5
EXPERIENCE_RESEED_COUNT = 4
DEFAULT_TRACK_RECORD_LENGTH = 1000

DEFAULT_INSTRUMENT = "EQUITY"
DEFAULT_DELAY = 1
DEFAULT_TRUNCATION = 0.08

NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"]
UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200"]
DECAYS = [0, 5, 10, 15, 20]


def _load_operator_metadata():
    operators_path = Path(__file__).with_name("operators.json")
    try:
        with operators_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


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


OPERATOR_METADATA = _load_operator_metadata()
ALLOWED_OPERATORS = sorted({op["name"] for op in OPERATOR_METADATA if "name" in op})
OPERATOR_CATEGORIES = {op["name"]: op.get("category") for op in OPERATOR_METADATA if "name" in op}
OPERATORS_BY_CATEGORY = {}
OPERATOR_ARITY = {}

for _operator in OPERATOR_METADATA:
    _name = _operator.get("name")
    if not _name:
        continue
    OPERATORS_BY_CATEGORY.setdefault(_operator.get("category"), []).append(_name)
    OPERATOR_ARITY[_name] = _infer_operator_arity(_operator.get("definition", ""))

TIME_SERIES_OPERATORS = OPERATORS_BY_CATEGORY.get("Time Series", [])
