# Brain Forge -- Run Report

_Generated 2026-06-08T20:28:00_

- Alphas recorded: **813**  (scored: **813**, unscored seeds: 0)
- Generations covered: **0 -> 1**
- Qualified (passed gates): **12**   |   Refined/tuned: **0**
- Best fitness: **0.4039**   |   Best Sharpe: **2.160**
- First record: 2026-06-07 19:39:36   |   Last record: 2026-06-08 20:24:13

## Evolution by generation

Rising best/mean fitness means the genetic engine is adding value; a flat line after the first few generations means it has plateaued.

| Gen      | N   | Best fit | Mean fit | Best Shp | Mean Shp | Mean turn | Mean depth | Qual |
| -------- | --- | -------- | -------- | -------- | -------- | --------- | ---------- | ---- |
| 0 (seed) | 692 | 0.4039   | 0.0099   | 2.130    | 0.448    | 0.303     | 7.4        | 6    |
| 1        | 121 | 0.0631   | -0.0105  | 2.160    | 0.867    | 0.282     | 8.9        | 6    |

## Seed vs evolved value-add

| Cohort          | N   | Best fit | Mean fit |
| --------------- | --- | -------- | -------- |
| Seeds (gen 0)   | 370 | 0.4039   | 0.0099   |
| Evolved (gen>0) | 121 | 0.0631   | -0.0105  |

Best-fitness delta (evolved - seed): **-0.3407** -> the GA did NOT beat the best seed -- check mutation/crossover.

## Structural diversity (scored population)

Heuristic shape analysis of the expressions actually scored. If 'multi-field' and 'turnover-gated' are near 0%, the population has collapsed onto single-field shapes and the rich templates are not surviving -- the lever is seed budget + mutation/crossover.

| Shape marker                         | % of scored |
| ------------------------------------ | ----------- |
| Multi-field (>=2 fields)             | 28.3        |
| Turnover-gated (trade_when)          | 14.5        |
| Term-structure spread (subtract/add) | 19.8        |
| Group-neutralized                    | 92.0        |
| VECTOR-collapsed (vec_avg/sum)       | 31.4        |
| ts_backfilled                        | 0.1         |

Field-count distribution: 0 field(s): 3, 1 field(s): 580, 2 field(s): 190, 3 field(s): 34, 4 field(s): 6

## Operator usage

| Operator         | Total uses | # alphas | % alphas |
| ---------------- | ---------- | -------- | -------- |
| group_neutralize | 960        | 748      | 92.0     |
| rank             | 553        | 411      | 50.6     |
| ts_zscore        | 547        | 387      | 47.6     |
| ts_rank          | 350        | 294      | 36.2     |
| vec_avg          | 266        | 247      | 30.4     |
| ts_delta         | 161        | 140      | 17.2     |
| subtract         | 134        | 124      | 15.3     |
| trade_when       | 124        | 118      | 14.5     |
| winsorize        | 75         | 71       | 8.7      |
| ts_decay_linear  | 67         | 67       | 8.2      |
| quantile         | 52         | 52       | 6.4      |
| ts_mean          | 45         | 45       | 5.5      |
| add              | 41         | 41       | 5.0      |
| ts_av_diff       | 38         | 38       | 4.7      |
| group_zscore     | 33         | 32       | 3.9      |
| zscore           | 31         | 30       | 3.7      |
| group_rank       | 17         | 17       | 2.1      |
| ts_quantile      | 16         | 16       | 2.0      |
| sign             | 15         | 15       | 1.8      |
| ts_std_dev       | 14         | 14       | 1.7      |

## Distribution

By universe: TOP3000: 813

By decay: 0: 378, 5: 147, 10: 73, 15: 148, 20: 67

## Top 40 alphas by fitness

| #  | Gen | Fitness | Sharpe | Turn  | Returns | OOS Shp | Depth | Qual | Tuned | Expression                                                                                    |
| -- | --- | ------- | ------ | ----- | ------- | ------- | ----- | ---- | ----- | --------------------------------------------------------------------------------------------- |
| 1  | 0   | 0.4039  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_impli... |
| 2  | 0   | 0.3261  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(zscore(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_imp... |
| 3  | 0   | 0.3045  | 1.950  | 0.537 | 0.0670  | -       | 13    | -    | -     | group_neutralize(trade_when(ts_zscore(sixth_event_option_effect, 180) > 0, quantile(group_... |
| 4  | 0   | 0.2920  | 2.000  | 0.371 | 0.0810  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 120) > 0, ts_zsc... |
| 5  | 0   | 0.2903  | 2.130  | 0.651 | 0.0898  | -       | 10    | -    | -     | group_neutralize(rank(group_zscore(rank(ts_rank(subtract(ninety_day_interpolated_implied_v... |
| 6  | 0   | 0.2785  | 1.960  | 0.361 | 0.0778  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 7  | 0   | 0.2650  | 2.130  | 0.651 | 0.0896  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_impli... |
| 8  | 0   | 0.2460  | 1.960  | 0.361 | 0.0778  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 9  | 0   | 0.2427  | 1.810  | 0.699 | 0.0753  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(atm_volatility_month3, vec_av... |
| 10 | 0   | 0.2373  | 2.080  | 0.563 | 0.0935  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_zscore(subtract(ninety_day_interpolated_imp... |
| 11 | 0   | 0.1648  | 1.460  | 0.382 | 0.1322  | -       | 8     | -    | -     | group_neutralize(-ts_zscore(subtract(second_month_highest_strike_price, vec_avg(ern4_60dor... |
| 12 | 0   | 0.1509  | 1.870  | 0.302 | 0.0705  | -       | 11    | -    | -     | group_neutralize(trade_when(ts_zscore(ten_day_interpolated_implied_volatility_2, 180) > 0,... |
| 13 | 0   | 0.1375  | 1.220  | 0.603 | 0.0870  | -       | 8     | -    | -     | group_neutralize(rank(ts_rank(add(ninety_day_interpolated_implied_volatility, vec_avg(ern4... |
| 14 | 0   | 0.1220  | 1.730  | 0.448 | 0.0572  | -       | 13    | -    | -     | group_neutralize(trade_when(ts_zscore(subtract(sixth_event_option_effect, one_thousand_day... |
| 15 | 0   | 0.1169  | 1.900  | 0.637 | 0.0893  | -       | 7     | -    | -     | group_neutralize(ts_zscore(winsorize(ts_rank(ninety_day_interpolated_implied_volatility, 6... |
| 16 | 0   | 0.1023  | 1.130  | 0.599 | 0.0864  | -       | 6     | -    | -     | group_neutralize(rank(ts_quantile(ninety_day_interpolated_implied_volatility, 60)), MARKET... |
| 17 | 0   | 0.1004  | 1.350  | 0.529 | 0.1252  | -       | 8     | -    | -     | group_neutralize(ts_zscore(-ts_zscore(vec_avg(ern4_m2histrike), 10), 15), SECTOR)             |
| 18 | 0   | 0.0975  | 1.160  | 0.600 | 0.0881  | -       | 6     | -    | -     | group_zscore(rank(ts_rank(ninety_day_interpolated_implied_volatility, 60)), MARKET)           |
| 19 | 0   | 0.0973  | 1.400  | 0.158 | 0.0768  | -       | 9     | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(add(ninety_day_interpolated_implied_vo... |
| 20 | 0   | 0.0960  | 1.750  | 0.360 | 0.0707  | -       | 8     | -    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 21 | 0   | 0.0902  | 1.620  | 0.999 | 0.0964  | -       | 12    | -    | -     | group_neutralize(quantile(group_neutralize(rank(ts_rank(group_neutralize(ts_delta(-ts_zsco... |
| 22 | 0   | 0.0900  | 1.580  | 0.958 | 0.0539  | -       | 7     | -    | -     | group_neutralize(ts_rank(rank(ts_av_diff(ninety_day_ex_announcement_implied_volatility, 18... |
| 23 | 0   | 0.0881  | 2.020  | 0.727 | 0.0819  | -       | 10    | -    | -     | group_neutralize(ts_delta(rank(rank(group_neutralize(rank(ts_rank(ninety_day_interpolated_... |
| 24 | 0   | 0.0879  | 1.740  | 0.153 | 0.0719  | -       | 8     | Y    | -     | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| 25 | 0   | 0.0850  | 1.900  | 0.665 | 0.0876  | -       | 9     | -    | -     | group_neutralize(rank(rank(group_neutralize(rank(ts_rank(ninety_day_interpolated_implied_v... |
| 26 | 0   | 0.0847  | 1.110  | 0.030 | 0.0720  | -       | 5     | -    | -     | group_zscore(rank(sixth_historical_announcement_effect), INDUSTRY)                            |
| 27 | 0   | 0.0833  | 1.630  | 0.627 | 0.0925  | -       | 6     | -    | -     | group_neutralize(winsorize(ts_rank(ninety_day_interpolated_implied_volatility, 60)), INDUS... |
| 28 | 0   | 0.0766  | 1.610  | 0.861 | 0.0746  | -       | 14    | -    | -     | group_neutralize(ts_av_diff(trade_when(ts_zscore(sixth_event_option_effect, 180) > 0, quan... |
| 29 | 0   | 0.0745  | 1.590  | 0.997 | 0.0942  | -       | 13    | -    | -     | group_neutralize(trade_when(ts_arg_min(sixth_event_option_effect, 180) > 0, quantile(group... |
| 30 | 0   | 0.0739  | 1.920  | 0.725 | 0.0665  | -       | 9     | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(ts_rank(ninety_day_interpolated_implie... |
| 31 | 0   | 0.0734  | 1.610  | 0.972 | 0.0947  | -       | 13    | -    | -     | group_neutralize(trade_when(ts_rank(sixth_event_option_effect, 180) > 0, quantile(group_ne... |
| 32 | 0   | 0.0690  | 1.810  | 0.863 | 0.0513  | -       | 11    | -    | -     | group_neutralize(rank(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_... |
| 33 | 0   | 0.0674  | 2.070  | 0.643 | 0.0794  | -       | 9     | -    | -     | group_neutralize(rank(group_rank(rank(ts_rank(ts_rank(ninety_day_interpolated_implied_vola... |
| 34 | 0   | 0.0662  | 1.660  | 0.991 | 0.1016  | -       | 12    | -    | -     | group_neutralize(quantile(group_neutralize(rank(ts_rank(group_neutralize(ts_delta(-ts_zsco... |
| 35 | 0   | 0.0661  | 1.790  | 0.298 | 0.0837  | -       | 10    | -    | -     | group_neutralize(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolated_impli... |
| 36 | 0   | 0.0651  | 1.080  | 0.030 | 0.0805  | -       | 5     | -    | -     | group_neutralize(winsorize(sixth_historical_announcement_effect), INDUSTRY)                   |
| 37 | 1   | 0.0631  | 2.110  | 0.692 | 0.1133  | -       | 12    | -    | -     | group_neutralize(rank(group_neutralize(group_neutralize(ts_zscore(-ts_zscore(subtract(seco... |
| 38 | 0   | 0.0594  | 1.040  | 0.030 | 0.0766  | -       | 5     | -    | -     | group_neutralize(scale(sixth_historical_announcement_effect), INDUSTRY)                       |
| 39 | 0   | 0.0581  | 1.070  | 0.029 | 0.0761  | -       | 5     | -    | -     | group_neutralize(quantile(sixth_historical_announcement_effect), INDUSTRY)                    |
| 40 | 0   | 0.0563  | 1.940  | 0.695 | 0.0744  | -       | 10    | -    | -     | group_neutralize(ts_rank(rank(rank(group_neutralize(rank(ts_rank(ninety_day_interpolated_i... |

## Qualified / submittable candidates

| Alpha ID | Fitness | Sharpe | Turn  | MaxCorr | Expression                                                                                    |
| -------- | ------- | ------ | ----- | ------- | --------------------------------------------------------------------------------------------- |
| 58vkQZQX | 0.0879  | 1.740  | 0.153 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| rKWPjxQo | 0.0440  | 1.630  | 0.105 | 0.000   | group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, 60) > 0, ts_zsco... |
| xAndQQxJ | 0.0239  | 1.520  | 0.111 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| rKWPzva8 | 0.0109  | 1.450  | 0.096 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| WjgVdYnQ | 0.0080  | 1.430  | 0.091 | 0.000   | group_neutralize(ts_mean(rank(group_neutralize(rank(ts_rank(subtract(ninety_day_interpolat... |
| Vk8350m0 | -0.0097 | 1.510  | 0.115 | 0.000   | group_neutralize(trade_when(ts_zscore(-ts_zscore(second_month_highest_strike_price, 10), 6... |
| ZYoKO9N0 | -0.0115 | 1.470  | 0.109 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| gJ38knVv | -0.0115 | 1.540  | 0.116 | 0.000   | group_neutralize(trade_when(ts_zscore(-ts_zscore(subtract(second_month_highest_strike_pric... |
| YPAv6L5M | -0.0125 | 1.480  | 0.099 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(-ts_zscore(second_month_highest_stri... |
| XgKoG135 | -0.0129 | 1.470  | 0.088 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(-ts_zscore(second_month_highest_stri... |
| RRrmJK9n | -0.0141 | 1.560  | 0.105 | 0.000   | group_neutralize(ts_decay_linear(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, ... |
| 58vkjLVz | -0.0188 | 1.290  | 0.133 | 0.000   | group_neutralize(ts_mean(ts_zscore(-ts_zscore(subtract(second_month_highest_strike_price, ... |
