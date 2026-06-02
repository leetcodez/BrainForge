import os
from dotenv import load_dotenv

load_dotenv()

# API Configurations
WQ_BASE_URL = os.getenv("WQ_BASE_URL", "https://api.worldquantbrain.com")
WQ_COOKIE = os.getenv("WQ_COOKIE", "cookieyes-consent=consentid:MnNBbnljSThGUWJQRkFSaE5SNXd1WmdJZXpTY1c0RG4,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; __zlcmid=1XjoXQxrdKEmm6w; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJPTzlXOG91VUZoSXRIYXAxZ0Z0S0hMRFFWS2FhM042OCIsImV4cCI6MTc4MDM2MjMwMSwiYW1yIjpbInB3ZCIsImZhY2UiXX0.GJ-p7Wwgay82JLC31Y5_S_BgpaL66w9u4wdulwr4hpk")

# Data Dictionary (Categorized)
PRICE_FIELDS = ["close", "open", "high", "low", "vwap", "adv20", "after_session_vwap", "after_hours_vwap_2", "after_hours_vwap_value"]
FUNDAMENTAL_FIELDS = [
    "abnormal_return_earnings_release", "accrued_liabilities_total", "accrued_liabilities_total_2",
    "accumulated_amortization_customer_intangibles", "accumulated_amortization_customer_intangibles_2",
    "accumulated_amortization_finite_intangibles", "accumulated_depreciation_depletion_amortization_ppne",
    "accumulated_oci_net_of_tax_value", "acquired_cash_equivalents_business_combination",
    "acquired_finite_intangible_assets", "acquired_finite_intangible_assets_total", "acquired_goodwill_value",
    "acquired_intangible_avg_useful_life", "acquired_property_equipment_value", "acquisition_assets_property_plant_equipment",
    "acquisition_goodwill_amount", "acquisition_identifiable_assets_recognized", "acquisition_liabilities_assumed",
    "acquisition_proforma_revenue", "acquisition_related_costs_expense", "acquisition_related_expenses",
    "acquisition_total_purchase_price", "acquisition_total_purchase_value", "actual_cashflow_per_share_value_quarterly",
    "actual_dividend_value_quarterly", "actual_earnings_per_share_2", "actual_earnings_per_share_3",
    "actual_earnings_per_share_4", "actual_earnings_per_share_value", "actual_earnings_per_share_value_2_1555",
    "actual_earnings_per_share_value_afterhours", "actual_eps_value", "actual_eps_value_2", "actual_eps_value_quarterly",
    "actual_return_on_pension_plan_assets", "actual_sales_value_annual", "actual_sales_value_quarterly",
    "adj_net_income_avg", "adj_net_income_median", "adj_net_income_stddev"
]
MOMENTUM_FIELDS = ["volume", "returns", "adjfactor", "actuals_reporting_currency", "actuals_value_currency_code", "advantageous_position_flag", "advantageous_position_flag_pre_filter"]

# Flat list for fallback
DATA_DICTIONARY = PRICE_FIELDS + FUNDAMENTAL_FIELDS + MOMENTUM_FIELDS

# Hardcoded Quant Library Templates
QUANT_TEMPLATES = [
    # Mean Reversion on Fundamentals
    "group_neutralize(rank(-ts_zscore({FUNDAMENTAL}, {LOOKBACK_SHORT})), {NEUTRALIZATION})",
    # Fundamental to Price Ratio
    "group_neutralize(rank({FUNDAMENTAL} / {PRICE}), {NEUTRALIZATION})",
    # Volatility Adjusted Momentum
    "group_neutralize(rank(ts_decay_linear(ts_rank({MOMENTUM}, {LOOKBACK_SHORT}), {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # Price Reversion
    "group_neutralize(rank(ts_rank({PRICE}, {LOOKBACK_SHORT}) - ts_rank({PRICE}, {LOOKBACK_LONG})), {NEUTRALIZATION})",
    # Cross-sectional Fundamental Momentum
    "group_neutralize(rank(ts_delta({FUNDAMENTAL}, {LOOKBACK_SHORT})), {NEUTRALIZATION})"
]

# Network Settings
BROWSER_IMPERSONATE = "chrome110" # curl_cffi impersonation string
MIN_JITTER_SECS = 1.0
MAX_JITTER_SECS = 3.0
MAX_CONCURRENT_SIMULATIONS = 5

# LLM Configurations
LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# Mutation & Genetic Evolution Settings
POPULATION_SIZE = 50
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
