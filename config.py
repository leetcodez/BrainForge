import os
from dotenv import load_dotenv

load_dotenv()

WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
WQ_COOKIE = os.getenv("WQ_COOKIE", "cookieyes-consent=consentid:MnNBbnljSThGUWJQRkFSaE5SNXd1WmdJZXpTY1c0RG4,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; __zlcmid=1XjoXQxrdKEmm6w; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJvOHM2ZWdSNDRDWjM5TmxaTW1sdVJWU201cGFEeTVGYSIsImV4cCI6MTc4MDQ4MzQ1MiwiYW1yIjpbInB3ZCIsImZhY2UiXX0.uc-YHWrXuAg1fMtevwCi1pLhil3eJ9a9qUBqWkMuwsM")

PRICE_FIELDS = ["close", "vwap", "open", "high", "low"]
VOLATILITY_FIELDS = ["implied_volatility_call_30", "implied_volatility_put_30", "implied_volatility_call_60", "implied_volatility_put_60"]
MACRO_FIELDS = ["mdl53_jc5_5year", "mdl53_jc5_1year", "mdl53_jc5_10year"]
SIZE_FIELDS = ["cap", "assets", "sales"]
FUNDAMENTAL_FIELDS = ["est_eps", "bookvalue_ps", "sales", "assets"]
SENTIMENT_FIELDS = ["news_short_interest"]
MOMENTUM_FIELDS = ["volume", "returns", "adjfactor"]

DATA_DICTIONARY = PRICE_FIELDS + VOLATILITY_FIELDS + MACRO_FIELDS + SIZE_FIELDS + FUNDAMENTAL_FIELDS + SENTIMENT_FIELDS + MOMENTUM_FIELDS

QUANT_TEMPLATES = [
    "group_neutralize(ts_mean(ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}) - ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), bucket(rank({SIZE}), range='0,1,0.1'))",
    "group_neutralize(ts_delta(ts_mean(ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}) - ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), bucket(rank({SIZE}), range='0,1,0.1'))",
    "group_neutralize(ts_decay_linear(group_rank(-1 * ts_delta(ts_zscore(ts_backfill({MACRO}, 2), {LOOKBACK_SHORT}) - ts_zscore(ts_backfill({MACRO}, 2), {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION}) / ts_std_dev(returns, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(ts_zscore(-1 * ts_delta(ts_zscore({MACRO}, {LOOKBACK_SHORT}) - ts_zscore({MACRO}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {LOOKBACK_LONG}) * ts_zscore({PRICE}, {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(ts_zscore({FUNDAMENTAL} / {PRICE}, {LOOKBACK_LONG}) * ts_zscore({SENTIMENT}, {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    "group_neutralize(ts_zscore({FUNDAMENTAL}, {LOOKBACK_LONG}) + ts_zscore(-1 * ts_delta({PRICE}, {LOOKBACK_SHORT}) / ts_delay({PRICE}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION})"
]

BROWSER_IMPERSONATE = "chrome110"
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5

LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6JDD_7raCiCjw8l3DdKFrhEAA5_kBWXP-ygPf3CVryPdA")

POPULATION_SIZE = 200
GENERATIONS = 500
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.45
TOURNAMENT_SIZE = 7
PARSIMONY_COEFFICIENT = 0.002

DEFAULT_INSTRUMENT = "EQUITY"
DEFAULT_DELAY = 1
DEFAULT_DECAY = 15
DEFAULT_NEUTRALIZATION = "SUBINDUSTRY"
DEFAULT_TRUNCATION = 0.08
