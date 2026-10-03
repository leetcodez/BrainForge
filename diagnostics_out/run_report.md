# Run Diagnostics - brain_memory.earnings4_run3
_dataset: earnings4  |  generated: 2026-06-18T05:03:14  |  scope: all_

DB: `brain_memory.earnings4_run3.db` | alphas analyzed: 1415 | trials (true N): 1415

## Run Health Scorecard
| Sub-score | Driver | Target | Value | Score (0-100) |
|---|---|---|---|---|
| Operator diversity | normalized operator entropy | > 0.6 | 0.587 | 97.8 |
| Field diversity | effective field count (1/HHI) | > 8 | 12.260 | 100.0 |
| Neutralization diversity | max single-neut share | < 0.5 | 0.903 | 19.4 |
| Behavioral independence | denoised ENB / #alphas | > 0.3 | 0.013 | 4.3 |
| Statistical validity | PBO (prob. backtest overfit) | < 0.3 | 0.583 | 59.5 |
| Search effectiveness | evolved vs best-seed fitness lift | > 0 | -0.939 | 0.0 |

**Overall health: 46.8 / 100**
**Vanity ratio: 76.7 qualified alphas per independent bet** (higher = more redundant headcount).

**Change vs previous run:** operator_entropy_norm +0.0, effective_field_count +0.0, max_neut_share +0.0, dsr_survival_rate_true_N +0.0, best_fitness_lift_vs_seed +0.0, overall_health -7.5

## Module 1 - Structural / monoculture
- Operator coverage: 0.567 (38/67 ops used); normalized entropy 0.587
- Zero-usage operators (29): abs, and, bucket, days_from_last_change, densify, equal, greater, greater_equal, group_backfill, group_mean, hump, if_else, is_nan, kth_element, less, less_equal, not, not_equal, or, power, reverse, signed_power, ts_corr, ts_count_nans, ts_covariance, ts_regression, ts_step, ts_sum, vector_neut
- Neutralization style: {'group_neutralize': 1278, 'none': 62, 'group_zscore': 50, 'group_rank': 16, 'group_scale': 9}
- Neutralization group key: {'MARKET': 663, 'SECTOR': 543, 'INDUSTRY': 81, 'SUBINDUSTRY': 66}
- Effective field count (1/HHI): 12.26; effective family count: 1.99
- Family distribution: {'earnings_event': 1519, 'options_vol': 1195, 'analyst': 4, 'unknown': 4, 'price_volume': 4}
- Archetypes: 771 distinct; max archetype share 0.019
- Top archetypes: {
"group_neutralize(ts_decay_linear(trade_when(ts_zscore(add(_, _), '_') > '_', trade_when(ts_zscore(vec_avg(_), '_') > trade_when(ts_zscore(vec_avg(_), '_') > '_', quantile(group_neutralize(normalize(vec_avg(_)), _)), -'_'), rank(_), -'_'), -'_'), '_'), _)": 27,
"group_neutralize(ts_zscore(_, '_'), _)": 25,
"group_neutralize(rank(_), _)": 22,
"group_neutralize(rank(vec_avg(_)), _)": 22,
"group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_zscore(_, '_'), -'_'), _)": 18,
"group_neutralize(-rank(_), _)": 17,
"group_neutralize(-rank(ts_mean(_, '_')), _)": 16,
"group_neutralize(ts_zscore(vec_avg(_), '_'), _)": 15,
"group_neutralize(rank(ts_rank(_, '_')), _)": 14,
"group_neutralize(rank(ts_zscore(vec_avg(_), '_')), _)": 13,
"group_neutralize(ts_delta(ts_delta(_, '_'), '_'), _)": 13,
"group_neutralize(-ts_zscore(_, '_'), _)": 13
}
- Depth {'n': 1415, 'min': 4.0, 'p25': 6.0, 'median': 8.0, 'mean': 8.079858657243816, 'p75': 9.0, 'max': 17.0}
- Turnover {'n': 1415, 'min': 0.0, 'p25': 0.013049999999999999, 'median': 0.057, 'mean': 0.11393477031802118, 'p75': 0.12795, 'max': 1.6211}
- Decay {'n': 1415, 'min': 0.0, 'p25': 0.0, 'median': 5.0, 'mean': 6.424028268551237, 'p75': 15.0, 'max': 20.0}
- Mean AST clone similarity: 0.373

## Module 2 - Behavioral independence (Effective Number of Bets)
### ALL with PnL
- matrix: 175 alphas x 1234 days (coverage 1.000, q=N/T 0.142)
- **ENB raw 2.12 | ENB denoised 2.28** (MP lambda+ 1.89)
- PC1 share: raw 0.817 / denoised 0.817
- mean |corr|: 0.808; cluster count {'0.5': 1, '0.7': 1}
- Behavioral clusters (representative = highest-fitness member):
    - size 175: 6XELjpvG (fit 0.976, sharpe 1.820) archetype `group_neutralize(ts_mean(rank(_), '_'), _)`
### QUALIFIED with PnL
- matrix: 175 alphas x 1234 days (coverage 1.000, q=N/T 0.142)
- **ENB raw 2.12 | ENB denoised 2.28** (MP lambda+ 1.89)
- PC1 share: raw 0.817 / denoised 0.817
- mean |corr|: 0.808; cluster count {'0.5': 1, '0.7': 1}
- Behavioral clusters (representative = highest-fitness member):
    - size 175: 6XELjpvG (fit 0.976, sharpe 1.820) archetype `group_neutralize(ts_mean(rank(_), '_'), _)`

## Module 3 - Statistical validity
- DSR survivors (deflation prob >= 95%): 0/1415 at TRUE N=1415 (vs 0 at capped N=1000)
- DSR survival rate (true N): 0.000
- **PBO 0.583** over 252 CSCV partitions (10 blocks)
- **DATA GAP:** oos_sharpe is empty for the whole run -- IS->OOS decay cannot be validated. Wire OOS capture into the next run.
- Top alphas by true-N DSR:
    - e7rY8rMJ: DSR 0.121, MinTRL n/a yr
    - bl9mV7EM: DSR 0.119, MinTRL n/a yr
    - RRpRLApj: DSR 0.119, MinTRL n/a yr
    - 58vm3ZE5: DSR 0.104, MinTRL n/a yr
    - omYbw0xl: DSR 0.097, MinTRL n/a yr
    - omK7JvQb: DSR 0.095, MinTRL n/a yr
    - mLXGV9bx: DSR 0.063, MinTRL n/a yr
    - Xgpg2Yom: DSR 0.061, MinTRL n/a yr
    - A1wWWNVe: DSR 0.061, MinTRL n/a yr
    - O0pOkJ57: DSR 0.060, MinTRL n/a yr

## Module 4 - GA / search health
- Generations present: [0, 1, 2, 3, 4]
- Best-fitness lift vs seed: -0.9390
- Structural duplicate rate (wasted compute proxy): 0.168
- Per-generation collapse (gen: opEntropy / effFamilies / winnerRate / bestSharpe):
    - g0 (n=608): 0.562 / 1.96 / 0.194 / 1.870
    - g1 (n=236): 0.572 / 1.99 / 0.538 / 1.870
    - g2 (n=243): 0.581 / 2.01 / 0.461 / 1.880
    - g3 (n=253): 0.566 / 2.00 / 0.565 / 1.900
    - g4 (n=75): 0.552 / 1.89 / 0.507 / 1.920
- Lineage / mutation / origin:
    - lineage_concentration: {"parents_with_offspring": 162, "offspring_hhi": 0.012550078981708294, "effective_parent_count": 79.68077344035024, "top_parents": {"KPLMYYVE": 31, "LLR2E2kn": 26, "ZYo1XQ9Q": 26, "RRrwmO9z": 26, "58vd9Pl6": 25, "gJ3NVXEm": 25, "wpekWbN5": 24, "3qAvmGLz": 20}}
    - mutation_productivity: {"refine:correlation": {"beats_parent": 14, "evaluated": 209, "productivity": 0.06698564593301436}, "refine:sharpe": {"beats_parent": 17, "evaluated": 183, "productivity": 0.09289617486338798}, "crossover": {"beats_parent": 4, "evaluated": 168, "productivity": 0.023809523809523808}, "refine:turnover": {"beats_parent": 33, "evaluated": 153, "productivity": 0.21568627450980393}, "crossover+mutation": {"beats_parent": 2, "evaluated": 144, "productivity": 0.013888888888888888}, "universe_sweep": {"beats_parent": 4, "evaluated": 12, "productivity": 0.3333333333333333}, "negation": {"beats_parent": 1, "evaluated": 3, "productivity": 0.3333333333333333}}
    - origin_survival: {"refine": {"qualified": 148, "total": 634, "qualified_rate": 0.2334384858044164}, "ga": {"qualified": 27, "total": 396, "qualified_rate": 0.06818181818181818}, "unknown": {"qualified": 0, "total": 370, "qualified_rate": 0.0}, "universe_sweep": {"qualified": 0, "total": 12, "qualified_rate": 0.0}, "negation": {"qualified": 0, "total": 3, "qualified_rate": 0.0}}

## Module 5 - Grinold breadth ceiling
- not available (no ENB)

## Senior-dev caveats
- No single metric is a verdict. Read low ENB + high archetype concentration + negative GA lift TOGETHER.
- Behavioral numbers are only as good as PnL coverage (reported above). Denoised ENB is the honest headline; raw ENB overstates independence.
- Diagnostics describe; they do not fix. Record this baseline before changing the GA.
