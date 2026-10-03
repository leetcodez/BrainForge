<callout icon="🎯" color="blue_bg">
	**Bottom line.** Your `MaxCorr=0.000` column is a trap: it's correlation against an *empty* submitted pool, not pairwise among your 97 candidates. On the metric BRAIN actually enforces — **Pearson correlation of the daily PnL curve, hard-capped at 0.70** — almost all 97 are siblings of one `fivehundred_day_close_to_close_vol` volatility-gate. You don't have 97 submittable alphas; you have **\~3–6 statistically independent signals**. The submission problem is therefore a **maximum-weight independent set** on the PnL-correlation graph, solved greedily. The selector below tells you the truth, submits the most-orthogonal-highest-impact alpha first, and stops correlated siblings from burning your 0.70 budget. The deeper fix (more independent signals) is upstream diversity — but this selector extracts maximum value from what you already have.
</callout>
<empty-block/>
## 1) What BRAIN actually measures (and what it doesn't)
Grounded in WorldQuant's own docs + consultant write-ups. These are the rules the selector must respect:
<table fit-page-width="true" header-row="true">
<tr>
<td>Check</td>
<td>What it really is</td>
<td>Threshold</td>
<td>Implication for selection</td>
</tr>
<tr>
<td>**Self-correlation**</td>
<td>Pearson correlation of the **daily PnL curve** (not weights, not the expression) of the candidate vs **each alpha you have already submitted**. Uses the overlap of their PnL windows (\~recent OS window).</td>
<td>**\< 0.70** (max pairwise, not average)</td>
<td>This is THE constraint. Must be computed on PnL vectors, which you currently don't persist.</td>
</tr>
<tr>
<td>**Sharpe escape hatch**</td>
<td>A correlated alpha is still accepted if its Sharpe is **≥10% higher** than the incumbent it clashes with.</td>
<td>Sharpe ≥ 1.10 × incumbent</td>
<td>Within a sibling cluster, ALWAYS keep the single highest-Sharpe member — it can beat the ceiling against your own prior submissions.</td>
</tr>
<tr>
<td>**Prod-correlation** (consultants)</td>
<td>Same PnL correlation but against the **production pool** (everyone's submitted alphas).</td>
<td>Platform-set</td>
<td>You can't see prod PnL, so leave a buffer below 0.70 on self-corr to survive prod drift.</td>
</tr>
<tr>
<td>**Portfolio-shape caps**</td>
<td>Avoid **\>30%** of your submissions in one Region/Delay/Data-Category bucket; submit some Delay-0.</td>
<td>≤30% per bucket</td>
<td>Spread across field families + neutralizations, not just decorrelate.</td>
</tr>
<tr>
<td>**Submission is serial**</td>
<td>Each submission is checked against the set already submitted — it's path-dependent.</td>
<td>—</td>
<td>Order matters. Submit most-orthogonal-first; each submission tightens the budget for the rest.</td>
</tr>
</table>
<empty-block/>
**The single most important takeaway:** correlation is on **realized PnL**, so two alphas with *completely different expressions and field names* can still be 0.95-correlated if they're both long earnings-vol. Syntactic "one-per-field-family" (roadmap #4) is a cheap proxy; the **correct** filter is one-per-**PnL-cluster**. That requires persisting each alpha's daily PnL — see §5.
<callout icon="⚠️" color="yellow_bg">
</callout>
## 2) Diagnosis of your current run
Reading your `analyze_run.py` output through the PnL lens:
- **97 "qualified" is illusory for submission.** The qualified table is dominated by `group_neutralize(trade_when(ts_zscore(fivehundred_day_close_to_close_vol, …) …))` — same signal root, different decay/window/wrapper. These are **vol-gate siblings**; their PnL correlation will be \~0.9+. BRAIN will accept the first, then reject the rest on self-corr.
- **Your best-fitness alpha (0.4039, the ****`ninety_day_interpolated_implied_volatility`**** term-structure one) is NOT in the submittable list** (`Qual = -`, no alpha_id) — it fails the weight/concentration check. So your highest-*fitness* idea and your highest-*Sharpe* submittable idea are different families. Good — that's two independent roots already.
- **Distinct signal roots actually present** in the submittable set: (a) `fivehundred_day_close_to_close_vol` realized-vol gate \[Sharpe up to 2.58\]; (b) `put_call_slope_28d` skew gate \[`mLX5A9rX`\]; (c) `ten_day_iv_ex_announcement` gate \[`akO7olA9`\]; (d) `five_day_intraday_historical_volatility_2` \[`e7rzQqkg`\]; (e) `second_month_highest_strike_price` \[negative fitness\]; and outside the submittable set, the `ninety_day_interpolated_implied_volatility` term-structure family.
- **But all of these are earnings4 IV/vol signals** — so even across different roots, expect high PnL correlation. My honest estimate: after PnL-clustering you'll find **3–6 genuinely independent alphas**, possibly fewer. That is the real ceiling on this single-dataset run, and it's exactly the single-dataset monoculture flagged as roadmap #2/#5 on the review doc.
## 3) The selection problem, stated precisely
Given candidates each with a value score $`v_i`$ and a pairwise PnL-correlation matrix $`C`$, choose an **ordered** subset $`S`$ such that every pair in $`S`$ has $`|C_{ij}| < \tau`$ (with the Sharpe-10% exception), maximizing $`\sum_{i \in S} v_i`$.
<empty-block/>
This is **Maximum-Weight Independent Set** on the graph whose edges join pairs with $`|C_{ij}| \ge \tau`$. MWIS is NP-hard, but a **greedy correlation-budgeted knapsack** is what real desks use and is near-optimal here because the correlation graph is block-structured (tight sibling clusters, sparse between clusters). Don't over-engineer it into an RL/ILP solver — that's exactly the overfitting trap.
## 4) The algorithm
Five phases. Designed to bolt onto `submit_to_worldquant.py` + `db_manager.py`.
### Phase 0 — Persist PnL (the missing prerequisite)
You cannot do any of this without each alpha's daily PnL vector. BRAIN's simulation result already returns it; you're discarding it. Add a table and capture it at scoring time (see §5).
### Phase 1 — Build the candidate pool
Filter to: `is_qualified = 1` AND `failed_checks` empty AND `alpha_id` valid (not `MANUAL_SEED`) AND `fitness >= MIN_FITNESS_floor`. (This is your existing submission filter — keep it.)
### Phase 2 — Compute the PnL-correlation matrix
Pearson on daily PnL over the **overlapping OS window** (mirror BRAIN: use the recent out-of-sample window, not the full IS history, so your numbers track theirs). Use absolute correlation — a −0.95 short-sibling is just as redundant as +0.95.
### Phase 3 — Define IMPACT (not raw fitness)
Raw fitness here tops out at 0.40 and rewards in-sample luck. Score by **robustness-adjusted, payout-aligned** value:
```python
# decay penalty: how much Sharpe survives out-of-sample
decay   = min(1.0, oos_sharpe / max(sharpe, 1e-9)) if oos_sharpe else 0.70
# margin above the gate: barely-passing alphas count less
margin  = clip((fitness - MIN_FITNESS) / MIN_FITNESS, 0, 1)
impact  = fitness * decay * (1 + 0.25 * margin)
# hard prerequisites — these are gates, never soft scores
if not dsr_pass or failed_checks:    # must survive Deflated Sharpe + all checks
    impact = float('-inf')
```
Note: BRAIN's value-add/payout *rewards alphas uncorrelated with the prod pool*, so decorrelating isn't only about passing the gate — uncorrelated alphas literally **score higher**. Impact + decorrelation are aligned, not in tension.
### Phase 4 — Collapse statistical siblings, then greedily select
```python
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster

def select_submissions(cands, C, ids,
                       tau=0.50,          # working budget (buffer below 0.70)
                       hard=0.70):        # BRAIN's ceiling
    # 4a) cluster into PnL families; cut so within-cluster pairs are siblings
    D = 1.0 - np.abs(C)                    # distance = 1 - |corr|
    Z = linkage(squareform(D, checks=False), method='average')
    labels = fcluster(Z, t=1.0 - hard, criterion='distance')

    # 4b) one representative per family = the highest-impact member
    reps = []
    for k in set(labels):
        members = [c for c, l in zip(cands, labels) if l == k]
        reps.append(max(members, key=lambda a: a.impact))

    # 4c) greedy correlation-budgeted knapsack across reps
    reps.sort(key=lambda a: a.impact, reverse=True)
    selected = []
    for a in reps:
        if a.impact <= 0:
            continue
        if not selected:
            selected.append(a); continue
        clashes = [s for s in selected if abs(C[ids[a.id]][ids[s.id]]) >= tau]
        if not clashes:
            selected.append(a)                       # within budget
        elif a.sharpe >= 1.10 * max(s.sharpe for s in clashes):
            selected.append(a)                       # BRAIN's 10%-Sharpe escape hatch
    return selected
```
### Phase 5 — Order submissions by marginal diversification
Because submission is serial, submit the most-orthogonal-highest-impact alpha **first**:
```python
def order_for_submission(selected, C, ids):
    ordered = []
    pool = selected[:]
    # seed with the single highest-impact alpha
    ordered.append(max(pool, key=lambda a: a.impact)); pool.remove(ordered[0])
    while pool:
        # pick the one that adds most value while staying most orthogonal
        def marginal(a):
            maxc = max(abs(C[ids[a.id]][ids[s.id]]) for s in ordered)
            return a.impact * (1.0 - maxc)
        nxt = max(pool, key=marginal)
        ordered.append(nxt); pool.remove(nxt)
    return ordered
```
Then enforce the **portfolio-shape caps** as a final pass: walk the ordered list and skip any alpha that would push a Region/Delay/Data-Category bucket past 30%.
## 5) Schema + integration changes
<table fit-page-width="true" header-row="true">
<tr>
<td>Where</td>
<td>Change</td>
<td>Why</td>
</tr>
<tr>
<td>`db_manager.py`</td>
<td>New table `alpha_pnl(alpha_id TEXT, dates JSON, pnl JSON)` (or a long `alpha_pnl_daily(alpha_id, date, pnl)`). Populate from the BRAIN sim result at scoring time.</td>
<td>PnL is the ONLY input the real correlation needs; you currently discard it.</td>
</tr>
<tr>
<td>`db_manager.py`</td>
<td>Add `dsr_pass` (bool) if not already persisted; you already store `oos_sharpe`.</td>
<td>Used as a hard prerequisite in the impact score.</td>
</tr>
<tr>
<td>`submit_to_worldquant.py`</td>
<td>Before the submit loop: load qualified pool → build `C` from `alpha_pnl` → run `select_submissions` → `order_for_submission`. Submit in that order.</td>
<td>Replaces "top-N by fitness" with decorrelated selection.</td>
</tr>
<tr>
<td>`submit_to_worldquant.py`</td>
<td>Add a **live pre-check**: before each submit, recompute self-corr of the candidate vs the alphas you've *already submitted this run*; skip if ≥ `tau` (unless the 10%-Sharpe hatch applies). Optionally call BRAIN's own correlation-check endpoint as ground truth.</td>
<td>Self-corr is serial; your local view must update after every successful submit.</td>
</tr>
<tr>
<td>`config.py`</td>
<td>`SUBMIT_CORR_BUDGET = 0.50`, `SUBMIT_CORR_HARD = 0.70`, `SUBMIT_MAX_PER_BUCKET = 0.30`, `SUBMIT_FITNESS_FLOOR` (reuse existing).</td>
<td>Make the thresholds tunable, not magic numbers.</td>
</tr>
</table>
<empty-block/>
<callout icon="🔧" color="gray_bg">
	**Why ****`tau = 0.50`****, not 0.69.** Three reasons: (1) you can't see the prod pool, so you need headroom for prod-correlation; (2) your own future submissions tighten the budget; (3) self-corr is estimated on a finite OS window and drifts as data updates daily. Submitting at 0.69 means the next daily refresh can retroactively push you over. 0.50–0.60 is the safe operating band.
</callout>
## 6) Applied to your current candidates (illustrative)
You must run it on real PnL, but from the expression structure the selection will look like this:
- **Submit #1:** `RRr76jw1` (or `O0978ldY`, identical) — the `fivehundred_day_close_to_close_vol` 120-day gate, **Sharpe 2.58**, the highest-Sharpe member of the dominant family. One submission represents the entire vol-gate cluster.
- **Submit #2:** the `put_call_slope_28d` alpha (`mLX5A9rX`) — different signal economics (skew, not realized vol); check its PnL-corr to #1, likely passes.
- **Submit #3:** the `ten_day_iv_ex_announcement` alpha (`akO7olA9`) — ex-announcement IV, plausibly decorrelated from realized-vol and skew.
- **Candidate #4:** the `ninety_day_interpolated_implied_volatility` term-structure family (your best *fitness* root) — **but it currently fails the weight/concentration check**, so fix that first (it's the highest-information signal you have).
- **Everything else in the 97:** almost certainly collapses into the above clusters → do **not** submit; they'll fail self-corr and waste attempts.
<empty-block/>
Net: this run probably yields **2–4 good submissions**, not 10. That's not the selector failing — it's the selector correctly reporting that a single-dataset run produces correlated siblings. The way to get to 10+ independent submissions is the upstream work: decorrelated-exemplar seeding (#2) and cross-dataset mining (#5).
## 7) Pitfalls to avoid
- **Don't optimize average correlation.** BRAIN enforces **max** pairwise. A set with low average but one 0.8 pair still fails.
- **Don't submit by raw fitness.** It rewards IS luck and ignores the budget; you'll spend all 10 attempts on one cluster.
- **Don't build a mean-variance/RL combiner.** BRAIN judges each alpha individually against the ceiling — you're not deploying a privately-weighted basket (this is the AlphaForge mismatch on the review doc). Greedy MWIS is the right model.
- **Don't ignore sign.** Use `|corr|`; an inverted sibling is still redundant.
- **Don't forget the serial update.** Recompute self-corr against the *growing* submitted set after every successful submit, not once at the start.
- **Don't "abuse" the 10%-Sharpe rule to inflate count.** Submitting a weak alpha first, then ratcheting in correlated siblings each 10% higher (1.5 → 1.65 → 1.82 → …), *looks* like it multiplies submissions \~5×. It doesn't pay: BRAIN scores the **decorrelated marginal contribution**, so a chain of correlated siblings collapses to roughly **one alpha's worth** of value-add, and in any pooled/team correlation test the lower-Sharpe ones get **removed and re-scored out**. You'd also blow the 30%-per-bucket concentration cap and clutter your track record. The escape hatch is for **upgrading** a signal you already submitted (a strictly-better sibling arrives later), not for gaming the counter. Within a cluster, submit only the single best.
## Sources
- WorldQuant BRAIN fitness / submission mechanics — [https://jglazar.github.io/projects/wq_project/](https://jglazar.github.io/projects/wq_project/)
- Self-correlation = PnL-graph correlation, 2-yr window, 10%-Sharpe exception — [https://github.com/jglazar/notes/blob/main/quant_interview/alpha_ideas.md](https://github.com/jglazar/notes/blob/main/quant_interview/alpha_ideas.md)
- Submission criteria thresholds (Self-correlation \<0.7 PnL, weight/sub-universe tests) — [https://www.scribd.com/document/728780335/World-Quant-Brain-Alpha-Documentation](https://www.scribd.com/document/728780335/World-Quant-Brain-Alpha-Documentation)
- Serial submission + prod-correlation for consultants; pick-best-of-correlated-group — [https://zhuanlan.zhihu.com/p/1915099506304849861](https://zhuanlan.zhihu.com/p/1915099506304849861)
- Correlation-clustering for diversified subset selection (method analogue) — [https://ideas.repec.org/p/arx/papers/1511.07945.html](https://ideas.repec.org/p/arx/papers/1511.07945.html)