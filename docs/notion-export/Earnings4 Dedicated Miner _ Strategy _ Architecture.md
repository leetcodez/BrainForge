<callout icon="✅" color="green_bg">
	**Verdict:** Yes — run a *focused earnings4 campaign*. It's the single best shot at our first submittable (and first delay-0) alpha, for three concrete reasons: it's **uncrowded** (correlation gate stops fighting us), it ships **125 delay-0 fields** (reopens the D0 door we'd written off), and its **xern-pair structure** is exactly what tonight's spread-seeding work was built for. Treat it as a campaign, not a permanent monoculture — see the concentration risk at the bottom.
</callout>
## ⚠️ The vector trap — read this first
"Vector" means two unrelated things in this dataset, and conflating them produces sim errors:
<table header-row="true">
<tr>
<td>Concept</td>
<td>What it is</td>
<td>Operator</td>
<td>Role</td>
</tr>
<tr>
<td>**VECTOR data type**</td>
<td>Multiple values per stock per day (the earnings4 fields)</td>
<td>`vec_avg`, `vec_sum`, `vec_stddev`, `vec_max`…</td>
<td>**Reduce** to a matrix before *any* other operator. This is what "hooks up vector fields."</td>
</tr>
<tr>
<td>**`vector_neut`**** operator**</td>
<td>Acts on the cross-sectional alpha vector (signal across all stocks on a day)</td>
<td>`vector_neut`, `group_vector_neut`</td>
<td>**Orthogonalize** a finished signal against a risk factor → strips unwanted exposure → higher Sharpe.</td>
</tr>
</table>
Different jobs. `vec_avg` lets us *use* the data at all; `vector_neut` makes a working signal *cleaner*. Both are wired below.
## Why earnings4 is the right target (research-backed)
- **Uncrowded = the correlation gate relaxes.** Our biggest silent killer has been correlation (and our fail-closed check makes it stricter). Zero existing alphas ⇒ near-zero cross-submission correlation by construction.
- **125 delay-0 fields.** This reopens the D0 path we abandoned (USA had no usable D0 data). A genuine route to a delay-0 alpha, not a theoretical one.
- **The earnings effect is a real, documented premium.** The earnings-announcement premium is large and robust, with annualized Sharpe estimates of \~0.94 (value-weighted) to \~2.38 (equal-weighted) in the literature — far above the market's \~0.35. That's a strong prior that signals *exist* in this domain.
- **The structural edges this dataset exposes are all documented anomalies:**
	- **IV term-structure slope** positively predicts the cross-section of option returns (high-slope minus low-slope straddle portfolios earn significant returns).
	- **Implied-vs-realized (IV−RV) spread** / volatility risk premium — IV systematically overstates realized vol; the gap is tradeable.
	- **Post-earnings-announcement drift (PEAD)** — one of the oldest, most persistent anomalies; `ern4_ernmv1` is a clean drift proxy.
	- **xern decomposition** (earnings vs ex-earnings IV/HV) is exactly the "censored / ex-earnings IV" technique vol desks use to isolate the earnings premium.
- **Forecast family = low-turnover, high-margin.** Slow update cycle holds positions longer — directly helps our turnover floor and margin gates.
## The 8 families → operator playbook
<table header-row="true">
<tr>
<td>Family</td>
<td>Key fields</td>
<td>What works</td>
<td>What fights the data</td>
</tr>
<tr>
<td>Per-event move history</td>
<td>`ern4_ernmv1`…`ernmv12`</td>
<td>Step fields → `ts_delta`/`ts_zscore` catch *the event*; backfill 5; PEAD proxy</td>
<td>Treating them as continuous; no backfill</td>
</tr>
<tr>
<td>Aggregate move stats</td>
<td>`ern4_absavgernmv`, `ern4_ernmvstdev`</td>
<td>Denominators / normalisers</td>
<td>Standalone signals</td>
</tr>
<tr>
<td>Constant-maturity IV</td>
<td>`ern4_10div/30div/60div/90div`, `ern4_30dexerniv`</td>
<td>**xern spread** = implied earnings effect; level signals</td>
<td>—</td>
</tr>
<tr>
<td>Term structure (monthly ATM)</td>
<td>`ern4_m1atmiv`…`m4atmiv`, `ern4_m1dtex`</td>
<td>Cross-sectional **snapshot**: rank, or ratio vs fixed-tenor anchor (`30div`)</td>
<td>**`ts_delta`**** on rolling chain → fake monthly "drop"** (chain rolls slots)</td>
</tr>
<tr>
<td>Realised vol (±earnings)</td>
<td>`ern4_*clshv` / `*clshvxern`, `*dorhv`</td>
<td>**HV − HVxern gap** = realized earnings-vol share</td>
<td>—</td>
</tr>
<tr>
<td>Vol-surface shape</td>
<td>`ern4_slope`</td>
<td>Put-call slope; **pair** with another signal</td>
<td>Standalone (crowded field)</td>
</tr>
<tr>
<td>Forecast family</td>
<td>`ern4_fcsterneffct`, `ern4_erneffct1`, `ern4_impernmv90d`, `ern4_fairvol90d`, `ern4_fairxieevol90d`</td>
<td>**Gap between forecast and implied**; backfill 5; low turnover</td>
<td>Short-window `ts_delta` (recalibration noise)</td>
</tr>
<tr>
<td>Microstructure & timing</td>
<td>`ern4_avg20doptvolu`, `ern4_m1dtex`, `ern4_ernmnth`, `ern4_nexterntod`</td>
<td>Step/calendar clocks; volume as interest proxy</td>
<td>`ts_delta` on strike fields (`m1lostrike`) → fake jumps</td>
</tr>
</table>
<callout icon="📐" color="gray_bg">
	**Cross-cutting rules:** default neutralization = **INDUSTRY**; **backfill** sparse forecast/per-event fields (`ts_backfill(…, 5)`), not dense IV/HV; **avoid ****`ts_corr`**** between two earnings4 fields** (captures construction, not behaviour) — prefer `ts_regression` or a standardised spread.
</callout>
## Curated alpha battery (starter seeds)
Grounded in the doc's "most loaded objects" + the research above. Industry-neutral, sparse fields backfilled. (Field names/vector-typing assumed per the doc — a couple may already be matrix and not need `vec_avg`.)
**1. Front-month implied earnings share** — the dataset's flagship object:
```javascript
group_neutralize(subtract(vec_avg(ern4_30div), vec_avg(ern4_30dexerniv)), INDUSTRY)
```
**2. Realised earnings-vol share (HV − HVxern):**
```javascript
group_neutralize(subtract(vec_avg(ern4_1000dclshv), vec_avg(ern4_1000dclshvxern)), INDUSTRY)
```
**3. Forecast-vs-implied gap** — "the signal lives in the gap":
```javascript
group_neutralize(subtract(ts_backfill(vec_avg(ern4_fcsterneffct), 5), vec_avg(ern4_impernmv90d)), INDUSTRY)
```
**4. Post-earnings drift** (cleanest PEAD proxy, step field):
```javascript
group_neutralize(ts_backfill(vec_avg(ern4_ernmv1), 5), INDUSTRY)
```
**5. Reaction vs typical reaction** (normalised fingerprint):
```javascript
group_neutralize(divide(ts_backfill(vec_avg(ern4_ernmv1), 5), vec_avg(ern4_absavgernmv)), INDUSTRY)
```
**6. Term-structure slope as snapshot** (NOT ts_delta — ratio vs fixed anchor):
```javascript
group_neutralize(rank(divide(vec_avg(ern4_m1atmiv), vec_avg(ern4_30div))), INDUSTRY)
```
**7. Vol-surface slope paired** (slope alone is crowded):
```javascript
group_neutralize(multiply(rank(vec_avg(ern4_slope)), rank(subtract(vec_avg(ern4_30div), vec_avg(ern4_30dexerniv)))), INDUSTRY)
```
**8. vector_neut residual** — earnings share orthogonalized against the base IV level, so it captures the *earnings-specific* component, not "high-vol stock":
```javascript
group_neutralize(vector_neut(subtract(vec_avg(ern4_30div), vec_avg(ern4_30dexerniv)), vec_avg(ern4_30dexerniv)), INDUSTRY)
```
**9. Ex-earnings volatility risk premium** (IV−RV with earnings stripped):
```javascript
group_neutralize(subtract(vec_avg(ern4_30dexerniv), vec_avg(ern4_20dclshvxern)), INDUSTRY)
```
## Miner architecture — wiring vector fields into the generator
### A. VECTOR data-type handling (the real "hook up")
- **Capture field metadata at harvest.** The WQ data-fields API returns `type` (MATRIX/VECTOR) and `delay` per field. Store both in `seed_pool.json` / `data_fields.json` and fold into a `FIELD_TYPES` + `FIELD_DELAY` map in config.
- **Auto-reduce VECTOR fields.** Anywhere the harvester/orchestrator places a VECTOR field into an expression, wrap it in a `vec_` reducer (default `vec_avg`; diversify with `vec_sum`/`vec_stddev`/`vec_max` for shape variety). A raw VECTOR field may never be a direct argument to a non-`vec_` operator.
- **SyntaxValidator guard.** Add a rule: VECTOR field not enclosed in a `vec_` reducer ⇒ reject or auto-repair. Prevents the dominant error mode.
### B. `vector_neut` as an orthogonalization lever
- Add `vector_neut` / `group_vector_neut` as a **top-level wrapper lever** (like neutralization, but operator-level).
- Ship a small **factor library** the generator can orthogonalize against:
	- **Market beta:** `ts_regression(returns, group_mean(returns, 1, market), 252, rettype=2)`
	- **Size:** `rank(cap)`
	- **Base IV level:** `vec_avg(ern4_30dexerniv)` (ex-earnings IV) — the key one for this dataset.
- This is our most direct Sharpe lever: best Sharpe so far was 1.08 \< 1.25; stripping beta/size/base-IV exposure is exactly how you lift Sharpe without changing the core idea.
- Bonus: `vector_neut(...)` is a brand-new skeleton shape → helps the anti-monoculture cap.
### C. Per-family operator guards
Encode the family→operator table above as a curated `EARNINGS4_FAMILY_MAP` in config that the harvester + LLM seed prompt consult: step fields allow `ts_delta`; rolling-chain ATM fields are snapshot-only (no `ts_delta`); forecast/per-event fields get `ts_backfill(…, 5)`; xern twins auto-pair as spreads; ban `ts_corr` between two earnings4 fields.
### D. LLM reasoning seeds + skeleton diversity
Feed the 8-family logic into the reasoning-seed prompt (built tonight) so the LLM reasons *in-domain* ("this is a forecast field, so I trade the forecast-vs-implied gap, not its `ts_delta`"). The skeleton-diversity cap keeps any single shape (including the xern-spread) from taking over the population.
## Phased rollout
1. **Phase 0 — Prove it's minable.** Capture field `type`+`delay` at harvest; build the family map; hand-load the curated battery via `inject_seeds.py`; confirm sims don't error (vec reduction correct). *Fast, low-risk.*
2. **Phase 1 — Dedicated harvest + run.** earnings4-scoped harvest with auto-`vec_` wrapping, xern pairing, step-field guards. Run **delay-1, TOP3000, INDUSTRY-neutral** to prove the dataset is alpha-rich.
3. **Phase 2 — Lift Sharpe.** Add the `vector_neut` lever (beta/size/base-IV factors) + LLM reasoning seeds. Target Sharpe ≥ 1.25 and the margin/turnover gates.
4. **Phase 3 — Go for D0.** Promote D1 winners; re-test the winning expressions at **delay-0** on the 125 D0 fields.
## Honest risks / open decisions
- **Concentration.** Mining only earnings4 means most signals load on the same earnings/vol factor → internal correlation, and a single point of failure if the dataset gets crowded later. **Mitigation:** the `vector_neut`-against-base-IV residual (battery #8) forces *earnings-specific* residuals that decorrelate internally; keep the skeleton cap on. Verdict stands — the uncrowded + D0 upside outweighs it *for now*.
- **Field metadata dependency.** Everything in section A depends on the harvest actually returning `type`/`delay`. First implementation task is to confirm and persist that.
- **No new files constraint.** All of this lands as edits to existing modules (`field_harvester`, `config`, `llm_seed_generator`, `orchestrator`, `syntax_validator`, `inject_seeds`) — no new Python files.
## References
- [Earnings Announcement Premium — Quantpedia](https://quantpedia.com/strategies/earnings-announcement-premium)
- [Earnings Announcements and Systematic Risk (Wharton)](https://faculty.wharton.upenn.edu/wp-content/uploads/2012/04/Draft20111215p_edited.pdf)
- [Equity Volatility Term Structures and the Cross-Section of Option Returns (Vasquez)](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2694879_code1025183.pdf?abstractid=1944298&mirid=1)
- [Equity Term Structure and Option Returns — Alpha Architect](https://alphaarchitect.com/equity-term-structure-and-option-returns/)
- [Option Returns and the Cross-Sectional Predictability of Implied Volatility (Saretto)](https://www.cis.upenn.edu/~mkearns/finread/CrossOptions.pdf)
- [The relation between implied and realized volatility (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0304405X98000348)
- [Post–earnings-announcement drift — Wikipedia](https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement_drift)
- [Volatility around earnings (ex-earnings IV) — ORATS](https://orats.com/university/volatility-around-earnings)
- [Historical option volatility during earnings (censored IV) — SpiderRock](https://spiderrock.net/historical-option-volatility-data/)
- [WorldQuant seminar notes — vector operators & group_vector_neut](https://github.com/jglazar/notes/blob/main/quant_interview/worldquant_seminar.md)
\</content\>