# Run Diagnostics - brain_memory.earnings4_run2
_dataset: earnings4  |  generated: 2026-06-13T08:56:05  |  scope: all_

DB: `brain_memory.earnings4_run2.db` | alphas analyzed: 2432 | trials (true N): 2432

## Run Health Scorecard
| Sub-score | Driver | Target | Value | Score (0-100) |
|---|---|---|---|---|
| Operator diversity | normalized operator entropy | > 0.6 | 0.584 | 97.3 |
| Field diversity | effective field count (1/HHI) | > 8 | 7.930 | 99.1 |
| Neutralization diversity | max single-neut share | < 0.5 | 0.932 | 13.6 |
| Behavioral independence | denoised ENB / #alphas | > 0.3 | 0.021 | 7.0 |
| Statistical validity | PBO (prob. backtest overfit) | < 0.3 | 0.286 | 100.0 |
| Search effectiveness | evolved vs best-seed fitness lift | > 0 | -0.224 | 0.0 |

**Overall health: 52.8 / 100**
**Vanity ratio: 47.3 qualified alphas per independent bet** (higher = more redundant headcount).

## Module 1 - Structural / monoculture
- Operator coverage: 0.582 (39/67 ops used); normalized entropy 0.584
- Zero-usage operators (28): abs, and, bucket, days_from_last_change, densify, equal, greater, greater_equal, group_backfill, group_mean, hump, if_else, inverse, is_nan, kth_element, less, less_equal, log, not, not_equal, or, reverse, sqrt, ts_corr, ts_covariance, ts_regression, ts_step, vector_neut
- Neutralization style: {'group_neutralize': 2267, 'none': 94, 'group_zscore': 38, 'group_rank': 22, 'group_scale': 9, 'zscore': 2}
- Neutralization group key: {'INDUSTRY': 1335, 'SUBINDUSTRY': 513, 'SECTOR': 317, 'MARKET': 173}
- Effective field count (1/HHI): 7.93; effective family count: 1.48
- Family distribution: {'options_vol': 8424, 'earnings_event': 2123, 'price_volume': 9, 'analyst': 7, 'unknown': 7}
- Archetypes: 1484 distinct; max archetype share 0.009
- Top archetypes: {
"group_neutralize(-rank(_), _)": 23,
"group_neutralize(-ts_zscore(_, '_'), _)": 20,
"group_neutralize(rank(_), _)": 19,
"group_neutralize(trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), _)": 17,
"group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_zscore(_, '_'), -'_'), _)": 16,
"group_neutralize(trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_')), '_')), _))), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), _)": 16,
"group_neutralize(rank(ts_rank(_, '_')), _)": 15,
"group_neutralize(ts_zscore(_, '_'), _)": 15,
"group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)": 15,
"group_neutralize(rank(ts_zscore(vec_avg(_), '_')), _)": 14,
"group_neutralize(ts_delta(ts_delta(_, '_'), '_'), _)": 14,
"group_neutralize(rank(ts_zscore(_, '_')), _)": 14
}
- Depth {'n': 2432, 'min': 4.0, 'p25': 8.0, 'median': 11.0, 'mean': 11.303042763157896, 'p75': 15.0, 'max': 31.0}
- Turnover {'n': 2432, 'min': 0.0, 'p25': 0.0898, 'median': 0.19915, 'mean': 0.26323939144736846, 'p75': 0.37539999999999996, 'max': 1.5316}
- Decay {'n': 2432, 'min': 0.0, 'p25': 0.0, 'median': 0.0, 'mean': 4.8129111842105265, 'p75': 10.0, 'max': 20.0}
- Mean AST clone similarity: 0.400

## Module 2 - Behavioral independence (Effective Number of Bets)
### ALL with PnL
- matrix: 572 alphas x 1234 days (coverage 1.000, q=N/T 0.464)
- **ENB raw 10.03 | ENB denoised 12.08** (MP lambda+ 2.83)
- PC1 share: raw 0.570 / denoised 0.570
- mean |corr|: 0.554; cluster count {'0.5': 1, '0.7': 31}
- Behavioral clusters (representative = highest-fitness member):
    - size 511: 0m8RdJbv (fit 0.352, sharpe 2.960) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), _)`
    - size 15: 88LGR6ko (fit -0.027, sharpe 1.950) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 9: GrolLVo5 (fit -0.016, sharpe 1.640) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_quantile(ts_zscore(-ts_zscore(subtract(_, vec_avg(_)), '_'), '_'), '_'), -'_'), _)`
    - size 6: QPQO7pw5 (fit -0.027, sharpe 2.070) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_mean(trade_when(ts_backfill(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(rank(_), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), '_'), -'_'), _)`
    - size 4: KPLVJbnN (fit -0.028, sharpe 1.550) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(add(_, subtract(_, vec_avg(_))) > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 2: bl9r2Wx6 (fit -0.024, sharpe 2.220) archetype `group_neutralize(trade_when(ts_zscore(subtract(subtract(_, _), vec_avg(_)), '_') > '_', trade_when(ts_zscore(_, '_') > normalize(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 1: mLX5bAZE (fit -0.012, sharpe 1.340) archetype `group_neutralize(ts_decay_linear(trade_when(ts_zscore(_, '_') > group_neutralize(rank(ts_rank(_, '_')), _), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), '_'), _)`
    - size 1: 3qAp9nnO (fit -0.019, sharpe 1.420) archetype `group_neutralize(ts_rank(-trade_when(ts_zscore(_, '_') > '_', ts_zscore(subtract(_, vec_avg(_)), '_'), -'_'), '_'), _)`
    - size 1: O09rNZvY (fit -0.026, sharpe 1.460) archetype `group_neutralize(trade_when(group_neutralize(rank(ts_rank(_, '_')), _) > zscore(zscore(group_neutralize(rank(ts_rank(add(add(add(_, _), _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), _)`
    - size 1: e7rbGw3g (fit -0.029, sharpe 1.730) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`
    - size 1: ZYoa22Ax (fit -0.024, sharpe 1.910) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`
    - size 1: npWanJ6M (fit -0.022, sharpe 1.980) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`
### QUALIFIED with PnL
- matrix: 572 alphas x 1234 days (coverage 1.000, q=N/T 0.464)
- **ENB raw 10.03 | ENB denoised 12.08** (MP lambda+ 2.83)
- PC1 share: raw 0.570 / denoised 0.570
- mean |corr|: 0.554; cluster count {'0.5': 1, '0.7': 31}
- Behavioral clusters (representative = highest-fitness member):
    - size 511: 0m8RdJbv (fit 0.352, sharpe 2.960) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), _)`
    - size 15: 88LGR6ko (fit -0.027, sharpe 1.950) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 9: GrolLVo5 (fit -0.016, sharpe 1.640) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_quantile(ts_zscore(-ts_zscore(subtract(_, vec_avg(_)), '_'), '_'), '_'), -'_'), _)`
    - size 6: QPQO7pw5 (fit -0.027, sharpe 2.070) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', ts_mean(trade_when(ts_backfill(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(rank(_), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), '_'), -'_'), _)`
    - size 4: KPLVJbnN (fit -0.028, sharpe 1.550) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(add(_, subtract(_, vec_avg(_))) > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 2: bl9r2Wx6 (fit -0.024, sharpe 2.220) archetype `group_neutralize(trade_when(ts_zscore(subtract(subtract(_, _), vec_avg(_)), '_') > '_', trade_when(ts_zscore(_, '_') > normalize(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), _)`
    - size 1: mLX5bAZE (fit -0.012, sharpe 1.340) archetype `group_neutralize(ts_decay_linear(trade_when(ts_zscore(_, '_') > group_neutralize(rank(ts_rank(_, '_')), _), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), '_'), _)`
    - size 1: 3qAp9nnO (fit -0.019, sharpe 1.420) archetype `group_neutralize(ts_rank(-trade_when(ts_zscore(_, '_') > '_', ts_zscore(subtract(_, vec_avg(_)), '_'), -'_'), '_'), _)`
    - size 1: O09rNZvY (fit -0.026, sharpe 1.460) archetype `group_neutralize(trade_when(group_neutralize(rank(ts_rank(_, '_')), _) > zscore(zscore(group_neutralize(rank(ts_rank(add(add(add(_, _), _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(_, '_')), '_'), -'_'), _)`
    - size 1: e7rbGw3g (fit -0.029, sharpe 1.730) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`
    - size 1: ZYoa22Ax (fit -0.024, sharpe 1.910) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`
    - size 1: npWanJ6M (fit -0.022, sharpe 1.980) archetype `group_neutralize(trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > '_', trade_when(ts_zscore(_, '_') > zscore(zscore(group_neutralize(rank(ts_rank(add(add(_, _), vec_avg(_)), '_')), _))), ts_zscore(winsorize(ts_rank(subtract(_, vec_avg(_)), '_')), '_'), -'_'), -'_'), -'_'), _)`

## Module 3 - Statistical validity
- DSR survivors (deflation prob >= 95%): 0/2432 at TRUE N=2432 (vs 0 at capped N=1000)
- DSR survival rate (true N): 0.000
- **PBO 0.286** over 252 CSCV partitions (10 blocks)
- **DATA GAP:** oos_sharpe is empty for the whole run -- IS->OOS decay cannot be validated. Wire OOS capture into the next run.
- Top alphas by true-N DSR:
    - 0m8GdGAp: DSR 1.067, MinTRL n/a yr
    - O09zWZpp: DSR 0.919, MinTRL n/a yr
    - O09zXJwv: DSR 0.892, MinTRL n/a yr
    - MPxee7p6: DSR 0.866, MinTRL n/a yr
    - 3qAPoRkO: DSR 0.866, MinTRL n/a yr
    - xAnGvA1J: DSR 0.866, MinTRL n/a yr
    - 78dmd7j5: DSR 0.787, MinTRL n/a yr
    - wpeGNYw1: DSR 0.787, MinTRL n/a yr
    - mLX7KmP6: DSR 0.787, MinTRL n/a yr
    - ZYozg608: DSR 0.787, MinTRL n/a yr

## Module 4 - GA / search health
- Generations present: [0, 1, 2, 3, 4, 5]
- Best-fitness lift vs seed: -0.2241
- Structural duplicate rate (wasted compute proxy): 0.105
- Per-generation collapse (gen: opEntropy / effFamilies / winnerRate / bestSharpe):
    - g0 (n=692): 0.556 / 1.94 / 0.152 / 2.130
    - g1 (n=306): 0.572 / 1.54 / 0.529 / 2.220
    - g2 (n=339): 0.574 / 1.50 / 0.501 / 2.580
    - g3 (n=467): 0.565 / 1.50 / 0.649 / 3.120
    - g4 (n=515): 0.564 / 1.35 / 0.715 / 3.310
    - g5 (n=113): 0.558 / 1.44 / 0.770 / 3.330
- Lineage / mutation / origin:
    - lineage_concentration: NOT COMPUTABLE: no parent_id recorded. Add a parent_id TEXT column (written at offspring creation) to enable it.
    - mutation_productivity: NOT COMPUTABLE: needs parent_id + mutation_type. Add both (written at offspring creation) to measure which mutations beat their parent.
    - origin_survival: NOT COMPUTABLE: no origin/source tag. Add an origin TEXT column (seed / reseed / ga / negation / refine / universe_sweep) to track reseed survival.

## Module 5 - Grinold breadth ceiling
- not available (no ENB)

## Senior-dev caveats
- No single metric is a verdict. Read low ENB + high archetype concentration + negative GA lift TOGETHER.
- Behavioral numbers are only as good as PnL coverage (reported above). Denoised ENB is the honest headline; raw ENB overstates independence.
- Diagnostics describe; they do not fix. Record this baseline before changing the GA.
