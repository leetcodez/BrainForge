# Brain Forge -- Run Report

_Generated 2026-06-12T22:02:01_

- Alphas recorded: **2432**  (scored: **2432**, unscored seeds: 0)
- Generations covered: **0 -> 5**
- Qualified (passed gates): **572**   |   Refined/tuned: **0**
- Best fitness: **0.4039**   |   Best Sharpe: **3.330**
- First record: 2026-06-07 19:39:36   |   Last record: 2026-06-12 21:53:16

## Evolution by generation

Rising best/mean fitness means the genetic engine is adding value; a flat line after the first few generations means it has plateaued.

| Gen      | N   | Best fit | Mean fit | Best Shp | Mean Shp | Mean turn | Mean depth | Qual |
| -------- | --- | -------- | -------- | -------- | -------- | --------- | ---------- | ---- |
| 0 (seed) | 692 | 0.4039   | 0.0099   | 2.130    | 0.448    | 0.303     | 7.4        | 6    |
| 1        | 306 | 0.1525   | -0.0079  | 2.220    | 1.113    | 0.291     | 9.7        | 33   |
| 2        | 339 | 0.2453   | -0.0070  | 2.580    | 1.151    | 0.337     | 10.1       | 58   |
| 3        | 467 | 0.3523   | 0.0206   | 3.120    | 1.570    | 0.235     | 13.4       | 149  |
| 4        | 515 | 0.2811   | -0.0019  | 3.310    | 1.760    | 0.190     | 15.4       | 276  |
| 5        | 113 | 0.1797   | 0.0204   | 3.330    | 1.993    | 0.168     | 16.3       | 50   |

## Seed vs evolved value-add

| Cohort          | N    | Best fit | Mean fit |
| --------------- | ---- | -------- | -------- |
| Seeds (gen 0)   | 370  | 0.4039   | 0.0099   |
| Evolved (gen>0) | 1493 | 0.3523   | 0.0017   |

Best-fitness delta (evolved - seed): **-0.0515** -> the GA did NOT beat the best seed -- check mutation/crossover.

## Structural diversity (scored population)

Heuristic shape analysis of the expressions actually scored. If 'multi-field' and 'turnover-gated' are near 0%, the population has collapsed onto single-field shapes and the rich templates are not surviving -- the lever is seed budget + mutation/crossover.

| Shape marker                         | % of scored |
| ------------------------------------ | ----------- |
| Multi-field (>=2 fields)             | 68.6        |
| Turnover-gated (trade_when)          | 57.9        |
| Term-structure spread (subtract/add) | 59.1        |
| Group-neutralized                    | 94.5        |
| VECTOR-collapsed (vec_avg/sum)       | 60.3        |
| ts_backfilled                        | 0.3         |

Field-count distribution: 0 field(s): 11, 1 field(s): 753, 2 field(s): 403, 3 field(s): 265, 4 field(s): 150, 5 field(s): 193, 6 field(s): 287, 7 field(s): 280, 8 field(s): 82, 9 field(s): 8

## Operator usage

| Operator         | Total uses | # alphas | % alphas |
| ---------------- | ---------- | -------- | -------- |
| ts_zscore        | 4483       | 1771     | 72.8     |
| group_neutralize | 4309       | 2298     | 94.5     |
| ts_rank          | 3240       | 1692     | 69.6     |
| vec_avg          | 3023       | 1455     | 59.8     |
| add              | 2694       | 1057     | 43.5     |
| rank             | 2533       | 1730     | 71.1     |
| trade_when       | 2526       | 1408     | 57.9     |
| zscore           | 2369       | 1068     | 43.9     |
| subtract         | 1588       | 1167     | 48.0     |
| winsorize        | 1352       | 1209     | 49.7     |
| ts_decay_linear  | 240        | 238      | 9.8      |
| normalize        | 199        | 199      | 8.2      |
| ts_delta         | 194        | 170      | 7.0      |
| ts_mean          | 160        | 158      | 6.5      |
| group_zscore     | 128        | 125      | 5.1      |
| quantile         | 106        | 102      | 4.2      |
| scale            | 68         | 68       | 2.8      |
| ts_av_diff       | 67         | 67       | 2.8      |
| ts_std_dev       | 50         | 50       | 2.1      |
| ts_quantile      | 49         | 49       | 2.0      |

## Distribution

By universe: TOP3000: 2426, TOP1000: 2, TOP500: 2, TOP200: 2

By decay: 0: 1461, 5: 275, 10: 236, 15: 246, 20: 214

## Top 40 alphas by fitness

| #  | Gen | Fitness | Sharpe | Turn  | Returns | OOS Shp | Depth | Qual | Tuned | Expression                                                                                    |
| -- | --- | ------- | ------ | ----- | ------- | ------- | ----- | ---- | ----- | --------------------------------------------------------------------------------------------- |
| 1  | 0   | 0.4039  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_impli... |
| 2  | 3   | 0.3523  | 2.960  | 0.391 | 0.1230  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 3  | 3   | 0.3464  | 2.980  | 0.236 | 0.1072  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 4  | 0   | 0.3261  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(zscore(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_imp... |
| 5  | 0   | 0.3045  | 1.950  | 0.537 | 0.0670  | -       | 13    | -    | -     | group_neutralize(trade_when(ts_zscore(sixth_event_option_effect, 180) > 0, quantile(group_... |
| 6  | 0   | 0.2920  | 2.000  | 0.371 | 0.0810  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| 7  | 0   | 0.2903  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(rank(group_zscore(rank(ts_rank(subtract(ninety_day_interpolated_implied_v... |
| 8  | 4   | 0.2811  | 3.150  | 0.238 | 0.1116  | -       | 16    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 9  | 0   | 0.2785  | 1.960  | 0.361 | 0.0778  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 10 | 3   | 0.2676  | 2.960  | 0.391 | 0.1230  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 11 | 0   | 0.2650  | 2.130  | 0.651 | 0.0896  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_impli... |
| 12 | 0   | 0.2460  | 1.960  | 0.361 | 0.0778  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 13 | 2   | 0.2453  | 2.580  | 0.383 | 0.1069  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 14 | 2   | 0.2451  | 2.580  | 0.383 | 0.1069  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 15 | 0   | 0.2427  | 1.810  | 0.699 | 0.0753  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(atm_volatility_month3, vec_av... |
| 16 | 0   | 0.2373  | 2.080  | 0.563 | 0.0935  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_zscore(subtract(ninety_day_interpolated_imp... |
| 17 | 3   | 0.2341  | 3.010  | 0.230 | 0.1055  | -       | 16    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 18 | 3   | 0.2218  | 2.640  | 0.256 | 0.0990  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(market_implied_announcement_percent_move, 180) > 0, ... |
| 19 | 4   | 0.2214  | 3.160  | 0.230 | 0.1146  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 20 | 3   | 0.2153  | 2.820  | 0.398 | 0.1169  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| 21 | 3   | 0.2139  | 2.770  | 0.391 | 0.1166  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 22 | 3   | 0.2087  | 2.850  | 0.392 | 0.0936  | -       | 17    | Y    | -     | group_neutralize(rank(group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehund... |
| 23 | 2   | 0.2058  | 2.540  | 0.390 | 0.1037  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| 24 | 3   | 0.2000  | 2.950  | 0.237 | 0.1065  | -       | 16    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 25 | 3   | 0.1945  | 2.980  | 0.236 | 0.1072  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 26 | 3   | 0.1925  | 2.250  | 0.316 | 0.0898  | -       | 11    | Y    | -     | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| 27 | 3   | 0.1922  | 2.770  | 0.131 | 0.1191  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 28 | 3   | 0.1919  | 2.770  | 0.187 | 0.1209  | -       | 13    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 29 | 3   | 0.1917  | 2.250  | 0.316 | 0.0898  | -       | 11    | Y    | -     | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| 30 | 3   | 0.1898  | 3.120  | 0.236 | 0.1110  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 31 | 3   | 0.1861  | 2.870  | 0.238 | 0.1012  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 32 | 4   | 0.1850  | 3.310  | 0.216 | 0.1153  | -       | 17    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 33 | 5   | 0.1797  | 3.330  | 0.214 | 0.1137  | -       | 17    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 34 | 4   | 0.1779  | 3.250  | 0.231 | 0.1185  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 35 | 4   | 0.1763  | 3.200  | 0.222 | 0.1148  | -       | 16    | Y    | -     | group_neutralize(trade_when(ts_zscore(subtract(fivehundred_day_close_to_close_vol, event_m... |
| 36 | 4   | 0.1739  | 2.990  | 0.234 | 0.1065  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 37 | 4   | 0.1732  | 3.100  | 0.230 | 0.1121  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 38 | 4   | 0.1727  | 3.270  | 0.226 | 0.1182  | -       | 18    | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 39 | 3   | 0.1707  | 2.250  | 0.316 | 0.0898  | -       | 11    | Y    | -     | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| 40 | 4   | 0.1691  | 3.130  | 0.230 | 0.1129  | -       | 14    | Y    | -     | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |

## Qualified / submittable candidates

| Alpha ID | Fitness | Sharpe | Turn  | MaxCorr | Expression                                                                                    |
| -------- | ------- | ------ | ----- | ------- | --------------------------------------------------------------------------------------------- |
| 0m8RdJbv | 0.3523  | 2.960  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 2rKOW2X8 | 0.3464  | 2.980  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| Vk8MZ70M | 0.2811  | 3.150  | 0.238 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| xAnYW6Qb | 0.2676  | 2.960  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| RRr76jw1 | 0.2453  | 2.580  | 0.383 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| O0978ldY | 0.2451  | 2.580  | 0.383 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| QPQbNpKK | 0.2341  | 3.010  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| d5QOvL2E | 0.2218  | 2.640  | 0.256 | 0.000   | group_neutralize(trade_when(ts_zscore(market_implied_announcement_percent_move, 180) > 0, ... |
| pw7WR3dx | 0.2214  | 3.160  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 58vQeaVX | 0.2153  | 2.820  | 0.398 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| MPx1zepz | 0.2139  | 2.770  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 78dZoVlb | 0.2087  | 2.850  | 0.392 | 0.000   | group_neutralize(rank(group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehund... |
| KPL7mlb1 | 0.2058  | 2.540  | 0.390 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| zqWdmkkX | 0.2000  | 2.950  | 0.237 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| kqKoJL1g | 0.1945  | 2.980  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 1YgxNRQJ | 0.1925  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| xAnYGJPl | 0.1922  | 2.770  | 0.131 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| pw7PG35j | 0.1919  | 2.770  | 0.187 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| JjdxzRdE | 0.1917  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| rKW753kj | 0.1898  | 3.120  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| RRre169e | 0.1861  | 2.870  | 0.238 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| MPxee7p6 | 0.1850  | 3.310  | 0.216 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| O09zWZpp | 0.1797  | 3.330  | 0.214 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| KPL525P1 | 0.1779  | 3.250  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| Vk8mexZV | 0.1763  | 3.200  | 0.222 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(fivehundred_day_close_to_close_vol, event_m... |
| MPxgzwX6 | 0.1739  | 2.990  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| le05JwAN | 0.1732  | 3.100  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| wpe26zEY | 0.1727  | 3.270  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| d5QO3L5j | 0.1707  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| 88LGzmva | 0.1691  | 3.130  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |
| pw7a8o7X | 0.1690  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| qMX5Xwr1 | 0.1677  | 3.120  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 1Ygl61WX | 0.1650  | 3.100  | 0.222 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| O09NxQqd | 0.1648  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| j2g3Pw6O | 0.1636  | 2.260  | 0.317 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| O09W5Jzd | 0.1627  | 3.020  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| O09zXJwv | 0.1624  | 3.320  | 0.220 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 2rKwN68Z | 0.1620  | 3.060  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| N1Oap9Nq | 0.1620  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| E5Km2mq9 | 0.1613  | 3.210  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| npWeoZ2M | 0.1600  | 3.080  | 0.232 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| O097YV7d | 0.1600  | 2.350  | 0.369 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| akObgNXW | 0.1592  | 2.960  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| vRmAjqkb | 0.1591  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |
| xAnGvA1J | 0.1582  | 3.310  | 0.216 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 3qAPoRkO | 0.1578  | 3.310  | 0.216 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqWYjKMG | 0.1541  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| RRrl96gd | 0.1533  | 3.270  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| d5Q3YlKw | 0.1528  | 3.270  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 1YgKOopz | 0.1511  | 3.250  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| wpeZGowx | 0.1502  | 2.960  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| RRrbpEL0 | 0.1463  | 2.980  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| rKWN9Kpo | 0.1455  | 3.190  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| A130NXaE | 0.1431  | 2.590  | 0.394 | 0.000   | group_neutralize(rank(group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehund... |
| d5Q3wO7j | 0.1411  | 3.210  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| P01YErlJ | 0.1405  | 3.210  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| qMX7XO7j | 0.1405  | 3.090  | 0.223 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 3qAPobO0 | 0.1403  | 3.230  | 0.209 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| wpeNNkZv | 0.1399  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| xAnj3arJ | 0.1389  | 2.300  | 0.370 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| omYaqMJv | 0.1381  | 2.980  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| d5QbPAbK | 0.1374  | 2.970  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| LLRN5N62 | 0.1373  | 2.910  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 9qRlRqVx | 0.1368  | 2.900  | 0.132 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| qMXxGxvv | 0.1360  | 2.960  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(ra... |
| A13z8W2w | 0.1354  | 3.250  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| E5KzKMVK | 0.1344  | 3.170  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| gJ3rXM1O | 0.1336  | 2.860  | 0.089 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| rKWN09Q8 | 0.1288  | 3.100  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| le0gW97e | 0.1261  | 3.090  | 0.223 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 88LNLJRv | 0.1251  | 3.010  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| kqKW9zz8 | 0.1246  | 3.150  | 0.209 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| A13NVYvE | 0.1246  | 2.920  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| O09Wx6Op | 0.1246  | 2.870  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| e7ra0eQO | 0.1243  | 3.010  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| Grodjo3o | 0.1233  | 2.510  | 0.378 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| P017gQox | 0.1228  | 2.350  | 0.369 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| YPAbx9EM | 0.1224  | 2.910  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| P01zLlVx | 0.1217  | 3.190  | 0.191 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, weeks_until_... |
| P01ZzG07 | 0.1194  | 2.130  | 0.323 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| gJ3QexdQ | 0.1193  | 2.120  | 0.285 | 0.000   | group_neutralize(trade_when(ts_zscore(add(add(one_thousand_day_ex_announcement_intraday_vo... |
| ZYozdoQ3 | 0.1191  | 3.230  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| wpeGNYw1 | 0.1187  | 3.280  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| Vk8GE395 | 0.1172  | 2.220  | 0.460 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| 6XEMlzXE | 0.1172  | 2.770  | 0.178 | 0.000   | group_neutralize(trade_when(ts_zscore(best_fit_implied_announcement_effect, 180) > 0, trad... |
| mLX7KmP6 | 0.1169  | 3.280  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| ZYozg608 | 0.1169  | 3.280  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| le0gYwk8 | 0.1167  | 2.810  | 0.233 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| E5KmveX1 | 0.1140  | 3.050  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| bl9xRggp | 0.1136  | 3.060  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| vRmkEwoG | 0.1129  | 2.510  | 0.378 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 78dmd7j5 | 0.1119  | 3.280  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| E5KmPxdP | 0.1118  | 2.990  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |
| 1YgXzZ36 | 0.1115  | 2.820  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 3qAkWxmP | 0.1110  | 3.130  | 0.218 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| N1OaVl5L | 0.1095  | 2.650  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| WjglWqQQ | 0.1091  | 2.700  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| E5Kz6Qv0 | 0.1075  | 3.180  | 0.213 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| QPQ70gmQ | 0.1064  | 2.540  | 0.352 | 0.000   | group_neutralize(group_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) >... |
| zqWkbEOV | 0.1053  | 2.340  | 0.173 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqW8L1MG | 0.1052  | 2.730  | 0.089 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| E5K8NMp0 | 0.1047  | 3.140  | 0.218 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| e7r1VRXO | 0.1035  | 2.920  | 0.393 | 0.000   | group_neutralize(rank(group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehund... |
| LLR8wXGe | 0.1025  | 2.890  | 0.393 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 6XE062XO | 0.1005  | 3.150  | 0.210 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqWA9KgE | 0.0979  | 2.900  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| omYLmQ3J | 0.0973  | 2.410  | 0.380 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqW8kj6d | 0.0950  | 2.560  | 0.192 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| zqW89E3X | 0.0941  | 2.750  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| E5KzMGg1 | 0.0940  | 3.100  | 0.211 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| QPQbK6pr | 0.0933  | 2.690  | 0.110 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| d5Q9KAjv | 0.0929  | 2.890  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 0m8N2e7k | 0.0911  | 3.040  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| Vk86bR0J | 0.0903  | 2.420  | 0.380 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| pw7MGk2j | 0.0883  | 3.060  | 0.387 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| XgKvAPYb | 0.0882  | 3.110  | 0.228 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 58vkQZQX | 0.0879  | 1.740  | 0.153 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| MPxen3pM | 0.0868  | 3.160  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| 58vQPP0J | 0.0866  | 2.330  | 0.367 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| O09NZWdd | 0.0864  | 2.770  | 0.140 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| QPQNp3QQ | 0.0843  | 2.960  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 1YgwZlvM | 0.0836  | 2.270  | 0.383 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| xAn2wmOn | 0.0828  | 2.960  | 0.208 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(forecasted_put_call_slope, vec_avg(ern4_fcs... |
| P012JWWK | 0.0821  | 2.240  | 0.362 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| 6XEogOW5 | 0.0819  | 2.870  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| akObNMm2 | 0.0806  | 2.740  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| xAnlZjKb | 0.0783  | 2.980  | 0.391 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > -5, trade_when(ts_zscore(... |
| d5Qa0Ojv | 0.0774  | 2.690  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(add(put_call_slope_28d, straddle_price_pct_move_9), ... |
| vRmGdbWQ | 0.0767  | 3.150  | 0.238 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 9qRdMaVe | 0.0767  | 3.040  | 0.230 | 0.000   | group_neutralize(trade_when(ts_sum(fivehundred_day_close_to_close_vol, 120) > zscore(zscor... |
| QPQz8a8p | 0.0766  | 3.090  | 0.223 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| d5Q9GnpY | 0.0759  | 2.920  | 0.141 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > (ts_zscore(fivehundred_day... |
| GroQLOKP | 0.0757  | 2.750  | 0.195 | 0.000   | group_neutralize(trade_when(ts_zscore(onethousand_day_intraday_vol, 252) > 0, trade_when(t... |
| bl9blkKN | 0.0754  | 2.330  | 0.367 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| N1OzL39E | 0.0741  | 3.120  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 78dNLLK2 | 0.0739  | 2.630  | 0.091 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| E5KQlYaL | 0.0736  | 2.750  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| LLRm6AKv | 0.0725  | 2.910  | 0.240 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(su... |
| 3qAGpdoO | 0.0724  | 2.850  | 0.246 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(s... |
| E5KpNMJm | 0.0724  | 2.630  | 0.091 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| Vk87mW6Y | 0.0716  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| mLXjq0G9 | 0.0688  | 2.430  | 0.384 | 0.000   | group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close... |
| vRmjw7QA | 0.0675  | 2.430  | 0.384 | 0.000   | group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close... |
| O09zRlV1 | 0.0675  | 2.960  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| Vk86bAr8 | 0.0675  | 2.370  | 0.380 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| QPQGqG0G | 0.0667  | 2.200  | 0.464 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| j2gAnW8j | 0.0663  | 2.680  | 0.109 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| ZYo7AgrQ | 0.0656  | 2.240  | 0.120 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| pw7WpaMX | 0.0646  | 2.840  | 0.375 | 0.000   | group_neutralize(trade_when(ts_rank(add(add(eleventh_event_option_effect_2, ninety_day_int... |
| e7r9vzO6 | 0.0642  | 2.330  | 0.347 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| Jjd3dQjx | 0.0631  | 2.810  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| GromGmlo | 0.0629  | 2.740  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| RRr751q0 | 0.0616  | 2.350  | 0.398 | 0.000   | group_neutralize(group_scale(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) ... |
| kqKVoEzL | 0.0592  | 2.200  | 0.385 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| bl9zmmlm | 0.0588  | 2.860  | 0.214 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(add(five_day_close_vol_ex_announcement, put... |
| bl9aWrWK | 0.0572  | 2.670  | 0.128 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_... |
| e7rarMOd | 0.0565  | 2.740  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| QPQ3zqzM | 0.0563  | 1.940  | 0.282 | 0.000   | group_neutralize(trade_when(ts_zscore(add(one_thousand_day_ex_announcement_intraday_volati... |
| npW6KEEa | 0.0557  | 2.820  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| MPxaQaRr | 0.0553  | 2.640  | 0.106 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| QPQWKQdX | 0.0541  | 2.750  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |
| zqWANALR | 0.0523  | 2.820  | 0.307 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_std_dev(... |
| qMXjnGbA | 0.0519  | 2.360  | 0.394 | 0.000   | group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close... |
| P0123W6x | 0.0515  | 2.480  | 0.135 | 0.000   | group_neutralize(trade_when(ts_zscore(ninety_day_iv_ex_announcement, 120) > 0, trade_when(... |
| e7r9Zw2M | 0.0514  | 2.390  | 0.381 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| WjglpJkj | 0.0509  | 2.670  | 0.141 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| 88LlY7Ez | 0.0506  | 2.250  | 0.316 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| omY6b57J | 0.0490  | 2.300  | 0.384 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| MPx1vW19 | 0.0484  | 2.300  | 0.359 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 58vrwl3N | 0.0483  | 2.780  | 0.383 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| qMX7NOYv | 0.0479  | 2.680  | 0.109 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 0m8XG6p2 | 0.0470  | 2.570  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| gJ3GNglg | 0.0470  | 2.970  | 0.238 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 9qRdKvRq | 0.0462  | 2.850  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| kqKvP7zP | 0.0461  | 2.810  | 0.384 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 9qRd8R9o | 0.0461  | 2.940  | 0.136 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| gJ3gXY3K | 0.0456  | 2.870  | 0.214 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 88LNnoJa | 0.0453  | 2.600  | 0.334 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_arg_max(... |
| 2rKGgE1w | 0.0440  | 2.640  | 0.379 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| rKWPjxQo | 0.0440  | 1.630  | 0.105 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 0m8x7K8r | 0.0432  | 2.650  | 0.375 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| RRrl09Ej | 0.0423  | 2.770  | 0.233 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(add(put_call_slope_28d, seventh_historical_... |
| O09MvKz1 | 0.0418  | 2.880  | 0.136 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| O09Wo1ad | 0.0398  | 2.630  | 0.228 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| mLX5A9rX | 0.0395  | 2.000  | 0.245 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 252) > 0, trade_when(ts_zscore(f... |
| QPQzv0rG | 0.0395  | 2.950  | 0.131 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| RRrlz9vz | 0.0392  | 2.890  | 0.136 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| qMXj0klV | 0.0387  | 2.130  | 0.369 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| ZYod9Q5n | 0.0387  | 2.960  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| xAnlYkOn | 0.0370  | 2.770  | 0.140 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 58vQK56N | 0.0362  | 2.250  | 0.378 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| WjgoJV0O | 0.0361  | 2.890  | 0.136 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| xAnVzkjN | 0.0361  | 2.690  | 0.090 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| akOQ81O6 | 0.0353  | 2.920  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| zqWk01g1 | 0.0346  | 2.180  | 0.323 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| zqWdWbEX | 0.0346  | 2.670  | 0.141 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| O09R1PE7 | 0.0344  | 2.780  | 0.286 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > trade_when(ts_zscore(add(... |
| E5Kp5QeJ | 0.0333  | 2.190  | 0.170 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| Vk8N625J | 0.0331  | 2.580  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| RRr5Ga5b | 0.0326  | 2.710  | 0.217 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| RRrz5Nzd | 0.0319  | 2.880  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| e7r1xJ3N | 0.0318  | 2.690  | 0.213 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| QPQW982M | 0.0317  | 2.710  | 0.137 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| RRr5KP0g | 0.0315  | 2.810  | 0.218 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| kqKoZvvL | 0.0313  | 2.430  | 0.135 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_60dclshv), 60) > 0, trade_when(ts_zscor... |
| akO7olA9 | 0.0312  | 2.170  | 0.211 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_iv_ex_announcement, 252) > 0, rank(group_neu... |
| qMXG20Oj | 0.0310  | 2.920  | 0.170 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_252dorhv), 120) > zscore(zscore(group_n... |
| E5KmR77R | 0.0310  | 2.590  | 0.215 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 88LjlG6o | 0.0307  | 2.490  | 0.096 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_... |
| vRmYXjwA | 0.0304  | 2.650  | 0.353 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_rank(add(... |
| LLRNERW2 | 0.0301  | 2.420  | 0.257 | 0.000   | group_neutralize(trade_when(ts_zscore(add(put_call_slope_28d, six_month_ex_announcement_im... |
| KPLVLGYE | 0.0296  | 2.670  | 0.109 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| xAnGn50n | 0.0292  | 2.880  | 0.240 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_erneffct2)... |
| 6XEjnx6K | 0.0289  | 2.140  | 0.360 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| 9qR8K3e1 | 0.0289  | 2.660  | 0.090 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| omYPRean | 0.0285  | 2.700  | 0.136 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| wpeGLAN1 | 0.0282  | 2.920  | 0.238 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 58vlNQmo | 0.0282  | 2.240  | 0.384 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| A13xP8wW | 0.0280  | 2.530  | 0.240 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ve... |
| kqKVzXo6 | 0.0279  | 2.140  | 0.358 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| wpea1rRQ | 0.0270  | 1.920  | 0.197 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| zqWYx9VO | 0.0255  | 2.170  | 0.197 | 0.000   | group_neutralize(trade_when(ts_zscore(second_month_forecasted_straddle_price, 180) > 0, tr... |
| QPQOlkNX | 0.0250  | 2.670  | 0.090 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| zqWk8AWG | 0.0249  | 2.090  | 0.170 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| rKWOj1vj | 0.0247  | 2.430  | 0.073 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| xAndQQxJ | 0.0239  | 1.520  | 0.111 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| 88L3YQ0o | 0.0235  | 2.040  | 0.246 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_absavgernmv), 180) > 0, trade_when(ts_z... |
| 6XErkQrP | 0.0227  | 2.100  | 0.361 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| qMX56wAV | 0.0226  | 2.590  | 0.217 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| rKWO1nL1 | 0.0220  | 2.120  | 0.367 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| Vk8mLEQY | 0.0217  | 2.880  | 0.140 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| YPA53ekM | 0.0216  | 2.200  | 0.166 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| N1OQQgbe | 0.0214  | 2.100  | 0.365 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| gJ3Xoxgm | 0.0210  | 2.720  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| kqKG3rpO | 0.0210  | 2.800  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| LLR9kXm6 | 0.0209  | 2.180  | 0.365 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| KPL7Jk9p | 0.0209  | 2.240  | 0.384 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| pw7aVZ6q | 0.0207  | 2.440  | 0.129 | 0.000   | group_neutralize(trade_when(ts_zscore(twenty_eight_day_ex_announcement_implied_volatility,... |
| MPxe9jqL | 0.0196  | 2.630  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| pw7MpLro | 0.0194  | 2.740  | 0.218 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| O09NVnvd | 0.0192  | 2.430  | 0.252 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_impernmv), 180) > 0, trade_when(ts_zsco... |
| Vk8mnAMw | 0.0186  | 2.740  | 0.106 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg... |
| ZYoXazej | 0.0185  | 2.570  | 0.382 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| d5QYEl2j | 0.0183  | 2.660  | 0.109 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| Vk8ZYY6M | 0.0181  | 2.680  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| d5QjZGPX | 0.0179  | 1.800  | 0.216 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| e7rzQqkg | 0.0179  | 2.040  | 0.192 | 0.000   | group_neutralize(trade_when(ts_zscore(five_day_intraday_historical_volatility_2, 180) > 0,... |
| xAnvnxJg | 0.0178  | 2.580  | 0.106 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| MPx7ggwn | 0.0176  | 2.220  | 0.145 | 0.000   | group_neutralize(group_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) >... |
| npWq3PK3 | 0.0172  | 2.890  | 0.146 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| zqW8NmQO | 0.0172  | 2.400  | 0.133 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_10div), 120) > 0, trade_when(ts_zscore(... |
| zqWAgePX | 0.0169  | 2.410  | 0.334 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, ts_rank(subtract(ninet... |
| d5QYZ1OX | 0.0153  | 2.690  | 0.379 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| GroX3QrQ | 0.0150  | 2.660  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 88LV87Pv | 0.0145  | 2.530  | 0.142 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_m2smoothstrpx), 252) > 0, trade_when(ts... |
| 1YgXqM3W | 0.0142  | 2.100  | 0.167 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| qMX57mb2 | 0.0141  | 2.660  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| A13L0b6E | 0.0131  | 2.640  | 0.106 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 3qAkGmm0 | 0.0118  | 2.790  | 0.216 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| O097nnbg | 0.0115  | 2.140  | 0.161 | 0.000   | group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close... |
| rKWPzva8 | 0.0109  | 1.450  | 0.096 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| d5Q33lav | 0.0107  | 2.760  | 0.187 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_500dorhvxern), 60) > 0, trade_when(ts_z... |
| LLRzErrM | 0.0102  | 2.750  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| WjgomEgo | 0.0102  | 2.720  | 0.102 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqWgWvEG | 0.0097  | 2.540  | 0.385 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| d5Q3Y0nY | 0.0094  | 2.770  | 0.102 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqWkYrvO | 0.0093  | 1.970  | 0.098 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| WjgVdYnQ | 0.0080  | 1.430  | 0.091 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| 1YgxAVa6 | 0.0080  | 2.180  | 0.365 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| e7r1VKwO | 0.0075  | 2.700  | 0.210 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 58vGgrNM | 0.0069  | 2.570  | 0.218 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| ZYoa0gq8 | 0.0068  | 2.390  | 0.143 | 0.000   | group_neutralize(trade_when(ts_zscore(second_month_days_to_expiry, 60) > 0, trade_when(ts_... |
| QPQ37x7p | 0.0066  | 1.900  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > group_neut... |
| zqWNQoEE | 0.0061  | 1.810  | 0.192 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| d5Qzdj32 | 0.0060  | 2.820  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| KPLv8WNx | 0.0059  | 2.660  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| pw7jRZPV | 0.0058  | 1.990  | 0.119 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| 78djmpj8 | 0.0054  | 2.030  | 0.315 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| wpeZZ2Gp | 0.0052  | 2.350  | 0.248 | 0.000   | group_neutralize(ts_av_diff(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(t... |
| 1YgOgOeK | 0.0049  | 2.600  | 0.388 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| A13Lr00Q | 0.0044  | 2.520  | 0.117 | 0.000   | group_neutralize(trade_when(ts_zscore(best_fit_implied_announcement_effect, 180) > 0, trad... |
| RRr5v5Qd | 0.0043  | 2.320  | 0.338 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, ts_rank(subtract(ninet... |
| npWqeQb3 | 0.0036  | 2.790  | 0.145 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_impernmvmth290d), 60) > 0, trade_when(t... |
| E5KpVYqJ | 0.0029  | 2.270  | 0.261 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| pw7MQ7Eq | 0.0028  | 2.640  | 0.088 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg... |
| wpeoJ6Jd | 0.0027  | 2.410  | 0.239 | 0.000   | group_neutralize(ts_zscore(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(t... |
| 3qAPOMXQ | 0.0025  | 2.800  | 0.131 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_30div), 252) > 0, trade_when(ts_zscore(... |
| KPLgEZ6x | 0.0017  | 2.430  | 0.079 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| QPQGlZYr | 0.0012  | 1.710  | 0.138 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| 9qR8zbW1 | 0.0008  | 2.570  | 0.089 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| bl9J98bZ | 0.0006  | 2.570  | 0.382 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 9qR86dOd | 0.0006  | 2.630  | 0.091 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| omYGEYKv | 0.0006  | 2.750  | 0.099 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| zqWNjd2V | 0.0003  | 1.690  | 0.103 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| pw7ajMjj | 0.0002  | 2.410  | 0.232 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| zqWk0YOE | 0.0001  | 1.970  | 0.172 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_m3dtex), 180) > 0, trade_when(ts_zscore... |
| O09Mjkzb | 0.0000  | 2.730  | 0.106 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| d5QbKv6x | -0.0004 | 2.330  | 0.216 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| bl9rMa3r | -0.0005 | 2.590  | 0.214 | 0.000   | group_neutralize(trade_when(ts_zscore(sixty_day_ex_announcement_close_volatility, 60) > 0,... |
| QPQ7zRXg | -0.0009 | 1.980  | 0.136 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| E5KNazr1 | -0.0011 | 2.620  | 0.079 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| 3qAll2mP | -0.0017 | 1.600  | 0.221 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| P01zMrdx | -0.0017 | 2.700  | 0.210 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| xAnYLWdN | -0.0020 | 1.920  | 0.074 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > group_neut... |
| 9qR8aqvK | -0.0022 | 2.590  | 0.106 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| N1OJE0YL | -0.0025 | 2.600  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 9qRVnzE2 | -0.0026 | 1.910  | 0.084 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > group_neu... |
| N1OaXZVp | -0.0027 | 2.000  | 0.117 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| Vk8azP98 | -0.0028 | 2.360  | 0.372 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| 58vr6XJJ | -0.0032 | 2.600  | 0.107 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(a... |
| 1YgwozPK | -0.0035 | 2.000  | 0.109 | 0.000   | group_neutralize(rank(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close... |
| 1YgXKLrW | -0.0038 | 2.240  | 0.395 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 1YgG8lEX | -0.0038 | 2.570  | 0.230 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 1Ygx8r9J | -0.0039 | 1.900  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > group_neut... |
| 3qAp33NZ | -0.0040 | 1.670  | 0.136 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| vRmp6NjQ | -0.0044 | 2.650  | 0.183 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| A13eYp7d | -0.0044 | 2.630  | 0.090 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| wpe2vOOQ | -0.0046 | 2.670  | 0.192 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_500dclshvxern), 60) > 0, trade_when(ts_... |
| gJ3r2pkO | -0.0049 | 2.530  | 0.077 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| E5K8PNvP | -0.0050 | 2.630  | 0.263 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| le0gPAOe | -0.0053 | 2.470  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| kqK8AGnz | -0.0054 | 2.410  | 0.422 | 0.000   | group_neutralize(trade_when(winsorize(ts_rank(subtract(ninety_day_interpolated_implied_vol... |
| 3qA1E59N | -0.0055 | 2.440  | 0.121 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| xAnvRrpJ | -0.0061 | 2.320  | 0.131 | 0.000   | group_neutralize(trade_when(ts_zscore(twenty_day_interpolated_iv, 180) > 0, trade_when(ts_... |
| GrozoGe0 | -0.0061 | 2.700  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 0m8g2e0G | -0.0063 | 2.750  | 0.229 | 0.000   | group_neutralize(ts_av_diff(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) ... |
| MPxzdPOn | -0.0066 | 2.730  | 0.231 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 58vlb0pk | -0.0071 | 1.700  | 0.102 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| 2rKlOPR6 | -0.0072 | 1.510  | 0.215 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| e7rz5pNO | -0.0073 | 1.960  | 0.159 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| omYqgKpb | -0.0076 | 1.710  | 0.096 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| E5Klpaxr | -0.0079 | 1.870  | 0.074 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zs... |
| QPQ3Roa5 | -0.0080 | 2.040  | 0.115 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| O09rLvJp | -0.0080 | 2.040  | 0.330 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 58vGm5mo | -0.0086 | 2.540  | 0.147 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| ZYoExWOx | -0.0086 | 1.600  | 0.098 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0... |
| omY6JeZJ | -0.0087 | 1.690  | 0.082 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_... |
| pw7xlXV3 | -0.0089 | 2.410  | 0.168 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| E5KmdOq0 | -0.0096 | 2.470  | 0.076 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| Vk8350m0 | -0.0097 | 1.510  | 0.115 | 0.000   | group_neutralize(trade_when(ts_zscore(-ts_zscore(second_month_highest_strike_price, 10), 6... |
| xAnY3gEn | -0.0103 | 1.580  | 0.073 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > group_neu... |
| P01zomdL | -0.0103 | 2.640  | 0.186 | 0.000   | group_neutralize(trade_when(ts_zscore(one_thousand_day_close_to_close_volatility, 180) > 0... |
| KPL5QWmk | -0.0104 | 2.610  | 0.131 | 0.000   | group_neutralize(trade_when(ts_zscore(fair_vol_month2_xiee_90d, 180) > 0, trade_when(ts_zs... |
| gJ3rGWLQ | -0.0106 | 2.500  | 0.084 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 5) > 0, trade_when(ts_zscore(fiv... |
| 3qAleg3Z | -0.0107 | 1.620  | 0.103 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| N1ObMR7w | -0.0107 | 1.700  | 0.152 | 0.000   | group_neutralize(ts_backfill(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) ... |
| mLX0AaqE | -0.0108 | 2.520  | 0.234 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ve... |
| 88LGZvMX | -0.0112 | 2.400  | 0.302 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(pu... |
| ZYoKO9N0 | -0.0115 | 1.470  | 0.109 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| gJ38knVv | -0.0115 | 1.540  | 0.116 | 0.000   | group_neutralize(trade_when(ts_zscore(-ts_zscore(subtract(second_month_highest_strike_pric... |
| RRr5pnNd | -0.0116 | 2.240  | 0.141 | 0.000   | group_neutralize(trade_when(ts_zscore(second_event_straddle_price_percent_of_equity_2, 252... |
| GrozXgoO | -0.0118 | 2.660  | 0.089 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| O096JZqJ | -0.0119 | 2.390  | 0.181 | 0.000   | group_neutralize(trade_when(ts_zscore(add(put_call_slope_28d, vec_avg(ern4_fairvol90d)), 1... |
| KPLv9W58 | -0.0120 | 2.570  | 0.385 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| XgKvNJez | -0.0120 | 2.610  | 0.092 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| wpe3zYW2 | -0.0120 | 2.490  | 0.091 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| mLX5bAZE | -0.0120 | 1.340  | 0.108 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| YPAv6L5M | -0.0125 | 1.480  | 0.099 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(-ts_zscore(second_month_highest_stri... |
| mLXj7Npx | -0.0125 | 1.840  | 0.094 | 0.000   | group_neutralize(trade_when(ts_zscore(add(fivehundred_day_close_to_close_vol, one_thousand... |
| YPA8gvMv | -0.0125 | 2.570  | 0.385 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| xAnj15pb | -0.0126 | 1.840  | 0.108 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| O09MMEqq | -0.0126 | 2.600  | 0.122 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_20dorhv), 120) > 0, trade_when(ts_zscor... |
| Vk8Gg91V | -0.0127 | 1.470  | 0.088 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| omYPxNab | -0.0129 | 2.370  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| npWag9rz | -0.0129 | 2.160  | 0.120 | 0.000   | group_neutralize(trade_when(ts_zscore(ninth_historical_straddle_price_percent, 60) > 0, tr... |
| XgKoG135 | -0.0129 | 1.470  | 0.088 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(-ts_zscore(second_month_highest_stri... |
| kqKP21gz | -0.0130 | 1.470  | 0.109 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| rKWNLGE9 | -0.0131 | 2.630  | 0.225 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| GroKVbAZ | -0.0133 | 2.570  | 0.246 | 0.000   | group_neutralize(ts_zscore(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) >... |
| bl9Qk82r | -0.0134 | 1.510  | 0.114 | 0.000   | group_neutralize(trade_when(ts_zscore(-ts_zscore(subtract(second_month_highest_strike_pric... |
| RRrmJK9n | -0.0141 | 1.560  | 0.105 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| d5QZXQpY | -0.0145 | 1.450  | 0.097 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(-ts_zscore(second_month_highest_strike_price... |
| 9qRpQK8x | -0.0146 | 1.590  | 0.116 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| YPA7varv | -0.0146 | 1.640  | 0.073 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| P0153Wnw | -0.0147 | 2.320  | 0.067 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| akO7Ejn1 | -0.0147 | 1.470  | 0.101 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| ZYoEGdNd | -0.0147 | 1.580  | 0.104 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| omYa9Jkl | -0.0148 | 2.230  | 0.271 | 0.000   | group_neutralize(ts_av_diff(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(... |
| E5KG3NEP | -0.0149 | 1.600  | 0.104 | 0.000   | group_neutralize(ts_backfill(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) ... |
| omYqqAeE | -0.0150 | 1.560  | 0.098 | 0.000   | group_neutralize(group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol,... |
| omYG0rmJ | -0.0151 | 2.670  | 0.085 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| JjdWl0pm | -0.0152 | 2.450  | 0.181 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 88Lp1NMX | -0.0154 | 1.560  | 0.105 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| E5KGJw0L | -0.0154 | 1.570  | 0.085 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| d5Q3mlLK | -0.0154 | 2.590  | 0.225 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| rKW0ZPjm | -0.0158 | 2.370  | 0.088 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_... |
| npWaO9q8 | -0.0160 | 2.200  | 0.062 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_... |
| GrolLVo5 | -0.0162 | 1.640  | 0.097 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_qua... |
| bl9jdblK | -0.0164 | 1.500  | 0.065 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, gro... |
| LLRGJ1X9 | -0.0166 | 1.530  | 0.072 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| JjdxAobx | -0.0167 | 1.660  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > group_neut... |
| pw7Ng6p3 | -0.0168 | 1.520  | 0.107 | 0.000   | group_zscore(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) ... |
| 6XEoZ8EY | -0.0172 | 2.550  | 0.070 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| 88Llbk6X | -0.0172 | 1.610  | 0.095 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| XgKo6dr0 | -0.0173 | 1.530  | 0.059 | 0.000   | group_neutralize(ts_decay_linear(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_clos... |
| 2rKGAoA6 | -0.0174 | 2.460  | 0.091 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| P01G9pWw | -0.0174 | 1.490  | 0.083 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| RRrz5qk1 | -0.0175 | 2.620  | 0.097 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_... |
| kqKjKrrK | -0.0175 | 1.610  | 0.095 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| d5Q399n2 | -0.0175 | 2.510  | 0.201 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 1YgOaagm | -0.0175 | 2.480  | 0.093 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| 78dzjLvO | -0.0177 | 1.260  | 0.104 | 0.000   | group_neutralize(-trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zs... |
| XgKoEPw8 | -0.0181 | 1.530  | 0.059 | 0.000   | group_neutralize(ts_mean(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_clo... |
| 58vkjLVz | -0.0188 | 1.290  | 0.133 | 0.000   | group_neutralize(ts_mean(ts_zscore(-ts_zscore(subtract(second_month_highest_strike_price, ... |
| N1OK833g | -0.0188 | 2.120  | 0.116 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_rank(add... |
| 6XEGQPEO | -0.0188 | 2.450  | 0.070 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| 3qAp9nnO | -0.0189 | 1.420  | 0.141 | 0.000   | group_neutralize(ts_rank(-trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0... |
| pw7R5j9q | -0.0189 | 2.000  | 0.236 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(su... |
| GroKY1gZ | -0.0190 | 2.460  | 0.242 | 0.000   | group_neutralize(ts_zscore(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_... |
| RRr7rkWz | -0.0193 | 1.540  | 0.095 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| 1YgXp0wJ | -0.0197 | 1.990  | 0.200 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_60dorhv), 120) > 0, trade_when(ts_zscor... |
| rKW9QoAo | -0.0197 | 2.310  | 0.224 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| RRr9J9rz | -0.0198 | 2.340  | 0.151 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_impliedee), 60) > 0, trade_when(ts_zsco... |
| A13rbWqe | -0.0203 | 2.490  | 0.066 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| 58vr60Kk | -0.0206 | 2.360  | 0.064 | 0.000   | group_neutralize(trade_when(ts_zscore(sixty_day_ex_announcement_close_volatility, 60) > 0,... |
| RRrlq5Rj | -0.0207 | 2.330  | 0.332 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(vec_avg(ern4_500dclshvxern), vec_avg(ern4_f... |
| 9qRXrQbK | -0.0209 | 1.520  | 0.079 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| QPQ0Vg1p | -0.0209 | 2.200  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 58vlAmeM | -0.0210 | 1.660  | 0.096 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| O09r2a8g | -0.0211 | 1.690  | 0.180 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| npWeqvex | -0.0211 | 2.470  | 0.222 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| E5K8MdzG | -0.0212 | 2.410  | 0.187 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(add(put_call_slope_28d, ten_day_interpolate... |
| vRmYZ75r | -0.0212 | 1.790  | 0.070 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| vRmjPp2A | -0.0215 | 1.370  | 0.115 | 0.000   | group_neutralize(ts_decay_linear(trade_when(rank(ts_rank(subtract(add(ninety_day_interpola... |
| npWanJ6M | -0.0216 | 1.980  | 0.128 | 0.000   | group_neutralize(trade_when(ts_zscore(seventh_historical_announcement_effect, 252) > 0, tr... |
| pw7xl6E3 | -0.0217 | 2.430  | 0.386 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| rKW0VkeJ | -0.0218 | 1.670  | 0.095 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| 2rKG6zAx | -0.0218 | 1.670  | 0.095 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 180) > 0, trade_when(ts_zscore(f... |
| mLXgAE82 | -0.0219 | 1.610  | 0.182 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 1YgGwG8W | -0.0219 | 2.210  | 0.134 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_ernstrapct5), 120) > 0, trade_when(ts_z... |
| XgK7KnRa | -0.0220 | 1.530  | 0.069 | 0.000   | group_neutralize(trade_when(ts_zscore(five_day_close_to_close_volatility, 120) > 0, trade_... |
| npWeYb8q | -0.0222 | 2.290  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fcsterneff... |
| wpeYArxd | -0.0224 | 1.950  | 0.165 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| e7rN2XeO | -0.0225 | 2.380  | 0.110 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| e7r9PqbE | -0.0225 | 1.620  | 0.182 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 6XEMePdO | -0.0228 | 2.070  | 0.157 | 0.000   | group_neutralize(trade_when(ts_zscore(two_hundred_fifty_two_day_close_to_close_volatility,... |
| O09rgj8Y | -0.0229 | 1.610  | 0.182 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| KPLvKXZk | -0.0230 | 2.110  | 0.097 | 0.000   | group_neutralize(trade_when(ts_zscore(market_implied_announcement_percent_move, 180) > 0, ... |
| 78djg5ZO | -0.0232 | 1.480  | 0.117 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_interpolated_implied_volatility_2, 180) > 0,... |
| P017YEqw | -0.0232 | 1.500  | 0.114 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(ten_day_interpolated_implied_volatility_2, ... |
| npW6a2YE | -0.0232 | 2.100  | 0.121 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| kqK8VwVk | -0.0233 | 2.120  | 0.120 | 0.000   | group_neutralize(trade_when(ts_zscore(first_event_straddle_price_percent_of_equity, 60) > ... |
| YPA80vpW | -0.0233 | 2.410  | 0.387 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| qMXjAY9v | -0.0234 | 1.340  | 0.056 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0... |
| ZYoa22Ax | -0.0235 | 1.910  | 0.126 | 0.000   | group_neutralize(trade_when(ts_zscore(eighth_event_straddle_price_percent_of_equity, 180) ... |
| pw7x7jPx | -0.0235 | 2.290  | 0.382 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| kqKveGxg | -0.0236 | 2.290  | 0.221 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| XgKz36w1 | -0.0236 | 2.600  | 0.133 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_m3atmiv), 60) > 0, trade_when(ts_zscore... |
| j2godb1e | -0.0236 | 2.390  | 0.080 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_m1atmiv), 60) > 0, trade_when(ts_zscore... |
| ZYozJmqj | -0.0240 | 2.070  | 0.107 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(one_year_interpolated_implied_volatility_2),... |
| npWmZKx3 | -0.0240 | 2.100  | 0.121 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| LLR802Ae | -0.0240 | 1.540  | 0.076 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ad... |
| bl9xKknl | -0.0240 | 2.250  | 0.059 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| bl9xOvpK | -0.0241 | 2.230  | 0.066 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_... |
| omYJeW95 | -0.0242 | 2.360  | 0.125 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_impernmvmth290d), 252) > 0, trade_when(... |
| MPx1VGqz | -0.0243 | 1.530  | 0.122 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| bl9r2Wx6 | -0.0243 | 2.220  | 0.289 | 0.000   | group_neutralize(trade_when(ts_zscore(subtract(subtract(put_call_slope_28d, sixty_day_inte... |
| 0m8Rj6G6 | -0.0244 | 1.420  | 0.138 | 0.000   | group_neutralize(trade_when(ts_zscore(group_neutralize(rank(group_neutralize(rank(ts_rank(... |
| P01ZKO1J | -0.0246 | 1.500  | 0.097 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| O09MKXJd | -0.0247 | 2.360  | 0.223 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg(ern4_fc... |
| xAnVPGbw | -0.0248 | 2.040  | 0.123 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| kqKjvVAP | -0.0251 | 1.480  | 0.117 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_interpolated_implied_volatility_2, 180) > 0,... |
| 9qR8Rp7d | -0.0251 | 2.280  | 0.173 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| GrolXAkP | -0.0254 | 1.500  | 0.117 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_interpolated_implied_volatility_2, 180) > 0,... |
| rKW9Jq79 | -0.0256 | 1.860  | 0.121 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| QPQOnmV5 | -0.0257 | 1.880  | 0.122 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| O09rNZvY | -0.0257 | 1.460  | 0.101 | 0.000   | group_neutralize(trade_when(group_neutralize(rank(ts_rank(ninety_day_interpolated_implied_... |
| j2gVJ0l9 | -0.0258 | 2.100  | 0.278 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(winsorize(ts... |
| E5KmNKMr | -0.0259 | 1.950  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(gr... |
| RRr90Z91 | -0.0259 | 2.180  | 0.224 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 58v5JPz5 | -0.0261 | 2.360  | 0.229 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(s... |
| 9qRGmXnK | -0.0262 | 1.900  | 0.100 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| Vk8MxrWw | -0.0262 | 2.110  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 9qRMewEV | -0.0265 | 2.510  | 0.226 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| Wjgo0Y6G | -0.0266 | 2.280  | 0.139 | 0.000   | group_neutralize(trade_when(ts_zscore(eighth_historical_announcement_percent_move, 252) > ... |
| j2gonJvj | -0.0269 | 2.010  | 0.122 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| d5QO6AJg | -0.0269 | 1.450  | 0.059 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| A13LxLrY | -0.0271 | 2.310  | 0.389 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| QPQO7pw5 | -0.0273 | 2.070  | 0.064 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| 88LGR6ko | -0.0274 | 1.950  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(w... |
| wpeNdJnp | -0.0274 | 2.330  | 0.221 | 0.000   | group_neutralize(trade_when(ts_zscore(add(put_call_slope_28d, straddle_price_pct_move_9), ... |
| JjdogZRA | -0.0274 | 2.340  | 0.065 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| QPQOaZNr | -0.0274 | 2.210  | 0.304 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_1000dclshvxern), 120) > 0, trade_when(t... |
| QPQOepOM | -0.0275 | 2.150  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| N1OLRjb7 | -0.0277 | 2.360  | 0.385 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| j2gV0KV9 | -0.0277 | 1.880  | 0.134 | 0.000   | group_neutralize(trade_when(ts_zscore(seventh_historical_event_percent_move, 252) > 0, tra... |
| xAnVXw5q | -0.0277 | 2.120  | 0.220 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| j2goQR6o | -0.0277 | 1.880  | 0.235 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(w... |
| O09R0p2g | -0.0278 | 1.780  | 0.077 | 0.000   | group_neutralize(trade_when(ts_zscore(zscore(group_neutralize(rank(ts_rank(add(add(elevent... |
| E5Kp23pJ | -0.0278 | 1.600  | 0.042 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| RRr9Wa91 | -0.0279 | 1.800  | 0.214 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(w... |
| KPLvnL7x | -0.0279 | 1.710  | 0.053 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, ... |
| RRr92eVg | -0.0279 | 1.700  | 0.063 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_wh... |
| pw7WWQrX | -0.0279 | 1.700  | 0.148 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| bl9J8VVm | -0.0280 | 1.710  | 0.148 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| xAnVb7Gg | -0.0280 | 1.700  | 0.148 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| A13evYKd | -0.0280 | 1.700  | 0.148 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| 0m8xrQGq | -0.0280 | 1.670  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(t... |
| KPLVJbnN | -0.0280 | 1.550  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(add(ninety_d... |
| P01xgvrK | -0.0280 | 1.640  | 0.147 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| 3qA1Xxz0 | -0.0280 | 1.620  | 0.144 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| qMXOZmwP | -0.0280 | 1.550  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(add(ninety_d... |
| ZYogA6v1 | -0.0280 | 1.580  | 0.114 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| qMXOEn01 | -0.0280 | 1.500  | 0.143 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| rKW9m2bj | -0.0280 | 1.460  | 0.085 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(add(ninety_d... |
| O09R8vKb | -0.0280 | 1.500  | 0.096 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ts... |
| A13ed3kY | -0.0280 | 1.400  | 0.083 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(add(ninety_... |
| A13LlKrE | -0.0281 | 1.920  | 0.113 | 0.000   | group_neutralize(trade_when(ts_zscore(twenty_day_average_option_volume, 252) > 0, trade_wh... |
| 9qR8Pv5e | -0.0282 | 2.120  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 58vr9g5k | -0.0284 | 2.210  | 0.059 | 0.000   | group_neutralize(trade_when(ts_zscore(third_historical_straddle_price_percent, 60) > 0, tr... |
| N1OLMq2e | -0.0285 | 2.110  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| e7rbGw3g | -0.0286 | 1.730  | 0.158 | 0.000   | group_neutralize(trade_when(ts_zscore(high_strike_month1, 120) > 0, trade_when(ts_zscore(p... |
| omYR2Pek | -0.0286 | 2.110  | 0.219 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| KPLvKrKj | -0.0290 | 1.900  | 0.076 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| 78d3gvKQ | -0.0290 | 2.090  | 0.220 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| vRmZa0m3 | -0.0292 | 2.090  | 0.225 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| omYRY6Q6 | -0.0292 | 2.140  | 0.119 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| YPA8dLxw | -0.0292 | 1.990  | 0.224 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(w... |
| 1YgXG76X | -0.0293 | 1.640  | 0.129 | 0.000   | group_neutralize(trade_when(ts_zscore(one_hundred_twenty_day_ex_announcement_close_to_clos... |
| Vk8mzX2J | -0.0294 | 2.360  | 0.268 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| YPA5O3GA | -0.0295 | 1.860  | 0.116 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > zscore(zsc... |
| QPQW0Nxr | -0.0295 | 1.770  | 0.058 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| Vk8MW6Z5 | -0.0296 | 1.780  | 0.062 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| 78dmo3g1 | -0.0296 | 2.420  | 0.269 | 0.000   | group_neutralize(ts_av_diff(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) ... |
| xAn2p3rb | -0.0298 | 2.390  | 0.230 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| 3qA19xw0 | -0.0298 | 1.770  | 0.058 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| O09z3jqv | -0.0298 | 1.930  | 0.047 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(subtract(put_call_slope_28d, vec_avg... |
| akOeLewv | -0.0300 | 1.600  | 0.059 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| le0Evvnl | -0.0300 | 1.520  | 0.117 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| 3qAPmE2O | -0.0300 | 2.530  | 0.267 | 0.000   | group_neutralize(ts_rank(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| 3qAPGM6z | -0.0304 | 2.220  | 0.200 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| j2gPG2V5 | -0.0310 | 2.250  | 0.064 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| 9qR8bQ8o | -0.0310 | 2.120  | 0.283 | 0.000   | group_neutralize(ts_delta(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_... |
| QPQNg9zM | -0.0311 | 2.250  | 0.064 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| zqW2GYZO | -0.0313 | 2.040  | 0.186 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| A13zxbvE | -0.0313 | 2.220  | 0.261 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| Vk8mmb1Y | -0.0314 | 1.970  | 0.174 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| LLREeZ79 | -0.0315 | 1.850  | 0.184 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| ZYodLvjZ | -0.0317 | 2.130  | 0.124 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_60dorhv), 180) > 0, trade_when(ts_zscor... |
| npWmKArx | -0.0318 | 1.770  | 0.058 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| xAnlGLKl | -0.0319 | 1.590  | 0.128 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_5dorhvxern), 180) > 0, trade_when(ts_zs... |
| E5Kzn55m | -0.0320 | 2.450  | 0.261 | 0.000   | group_neutralize(ts_zscore(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) >... |
| 3qAkdRgX | -0.0321 | 2.130  | 0.317 | 0.000   | group_neutralize(ts_zscore(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) >... |
| gJ3X9Kke | -0.0322 | 2.240  | 0.180 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| wpe2G2wY | -0.0323 | 2.160  | 0.282 | 0.000   | group_neutralize(ts_delta(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > ... |
| xAnGlr0g | -0.0324 | 2.230  | 0.064 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_... |
| KPLzgG0k | -0.0324 | 2.170  | 0.181 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| vRmZ99Pd | -0.0325 | 2.210  | 0.122 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_decay_lin... |
| 2rKGYW26 | -0.0326 | 2.160  | 0.063 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_ex_announcement_intraday_volatility, 120) > ... |
| 1YgGlONz | -0.0326 | 1.820  | 0.089 | 0.000   | group_neutralize(trade_when(ts_zscore(two_fifty_two_day_ex_announcement_intraday_volatilit... |
| 9qR8P0q1 | -0.0328 | 1.980  | 0.222 | 0.000   | group_neutralize(ts_av_diff(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(t... |
| Vk8meKZA | -0.0329 | 1.960  | 0.129 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_erneffct11), 60) > 0, trade_when(ts_zsc... |
| Vk8ZpdP8 | -0.0330 | 2.010  | 0.084 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| YPA8p996 | -0.0332 | 1.940  | 0.084 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| QPQNgMow | -0.0333 | 1.910  | 0.142 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_ernmv10), 120) > 0, trade_when(ts_zscor... |
| rKW9P6b8 | -0.0336 | 2.170  | 0.126 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| MPxzxgvL | -0.0336 | 2.000  | 0.047 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| omYRqweb | -0.0339 | 1.670  | 0.058 | 0.000   | group_neutralize(trade_when(ts_zscore(ten_day_intraday_historical_volatility, 60) > 0, ts_... |
| 58vrv62N | -0.0340 | 1.550  | 0.049 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| Wjg3VPMj | -0.0341 | 2.130  | 0.383 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 180) > zscore(zs... |
| A13zpG9d | -0.0341 | 2.200  | 0.222 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > zscore(zs... |
| 78d301Lx | -0.0343 | 2.220  | 0.073 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_w... |
| qMXG2j7A | -0.0346 | 2.080  | 0.170 | 0.000   | group_neutralize(trade_when(ts_zscore(vec_avg(ern4_ernstrapct10), 120) > zscore(zscore(gro... |
| bl9zgJmM | -0.0357 | 2.280  | 0.061 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
| YPAl8KAJ | -0.0358 | 2.370  | 0.227 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(fi... |
| 58vr3EpM | -0.0369 | 2.020  | 0.061 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_z... |
| wpeGA1Yd | -0.0376 | 2.030  | 0.135 | 0.000   | group_neutralize(trade_when(ts_zscore(ninety_day_close_to_close_volatility_2, 252) > 0, tr... |
| LLREdWq9 | -0.0376 | 1.920  | 0.102 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| 9qRGe91d | -0.0390 | 2.100  | 0.088 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_when(ts_zscore(f... |
| 78dGMzPZ | -0.0398 | 1.790  | 0.048 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(put_call_slope_28d, 120) > 0, trade_... |
| E5KmzvRr | -0.0458 | 1.760  | 0.087 | 0.000   | group_neutralize(trade_when(ts_zscore(put_call_slope_28d, 60) > 0, trade_when(ts_zscore(ve... |
| bl9xwOdR | -0.0500 | 1.530  | 0.042 | 0.000   | group_neutralize(ts_mean(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > z... |
