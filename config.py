import os
from dotenv import load_dotenv

load_dotenv()

# API Configurations
WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
WQ_COOKIE = os.getenv("WQ_COOKIE", "cookieyes-consent=consentid:MnNBbnljSThGUWJQRkFSaE5SNXd1WmdJZXpTY1c0RG4,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; __zlcmid=1XjoXQxrdKEmm6w; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJvOHM2ZWdSNDRDWjM5TmxaTW1sdVJWU201cGFEeTVGYSIsImV4cCI6MTc4MDQ4MzQ1MiwiYW1yIjpbInB3ZCIsImZhY2UiXX0.uc-YHWrXuAg1fMtevwCi1pLhil3eJ9a9qUBqWkMuwsM")

# Expanded Data Dictionary to support the seeds
PRICE_FIELDS = ["close", "vwap", "open", "high", "low"]
VOLATILITY_FIELDS = ["implied_volatility_call_30", "implied_volatility_put_30", "implied_volatility_call_60", "implied_volatility_put_60"]
MACRO_FIELDS = ["mdl53_jc5_5year", "mdl53_jc5_1year", "mdl53_jc5_10year"]
SIZE_FIELDS = ["cap", "assets", "sales"]
FUNDAMENTAL_FIELDS = ["actual_earnings_per_share_value", "accrued_liabilities_total"] # Keep some basics
MOMENTUM_FIELDS = ["volume", "returns", "adjfactor"]

DATA_DICTIONARY = PRICE_FIELDS + VOLATILITY_FIELDS + MACRO_FIELDS + SIZE_FIELDS + FUNDAMENTAL_FIELDS + MOMENTUM_FIELDS

# Elite Transfer Learning Seeds
QUANT_TEMPLATES = [
    # 1. The Options IV Skew Masterpiece (Your 2.56 Sharpe Seed)
    "group_neutralize(ts_mean(ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}) - ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), bucket(rank({SIZE}), range='0,1,0.1'))",
    
    # 2. The Options IV Skew (Momentum Variant)
    "group_neutralize(ts_delta(ts_mean(ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}) - ts_zscore({VOLATILITY}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), bucket(rank({SIZE}), range='0,1,0.1'))",

    # 3. The Macro Yield Curve Momentum (Your 1.50 Sharpe Seed, structurally neutralized)
    "group_neutralize(ts_decay_linear(group_rank(-1 * ts_delta(ts_zscore(ts_backfill({MACRO}, 2), {LOOKBACK_SHORT}) - ts_zscore(ts_backfill({MACRO}, 2), {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {NEUTRALIZATION}) / ts_std_dev(returns, {LOOKBACK_LONG}), {LOOKBACK_SHORT}), {NEUTRALIZATION})",
    
    # 4. The Macro Yield Curve (Z-Score Variant to force Long/Short balance)
    "group_neutralize(ts_zscore(-1 * ts_delta(ts_zscore({MACRO}, {LOOKBACK_SHORT}) - ts_zscore({MACRO}, {LOOKBACK_SHORT}), {LOOKBACK_SHORT}), {LOOKBACK_LONG}) * ts_zscore({PRICE}, {LOOKBACK_SHORT}), {NEUTRALIZATION})"
]

# Network Settings
BROWSER_IMPERSONATE = "chrome110" # curl_cffi impersonation string
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5

# LLM Configurations
LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6JDD_7raCiCjw8l3DdKFrhEAA5_kBWXP-ygPf3CVryPdA")

# Mutation & Genetic Evolution Settings
POPULATION_SIZE = 200
GENERATIONS = 500
ELITISM_RATIO = 0.1
MUTATION_RATE = 0.2
TOURNAMENT_SIZE = 5
PARSIMONY_COEFFICIENT = 0.05 # Penalizes AST depth to eliminate tree bloat

# Simulation Settings
DEFAULT_INSTRUMENT = "EQUITY"
DEFAULT_DELAY = 1
DEFAULT_DECAY = 15
DEFAULT_NEUTRALIZATION = "SUBINDUSTRY"
DEFAULT_TRUNCATION = 0.08
