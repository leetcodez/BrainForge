<callout icon="🎯" color="blue_bg">
	**The bet:** stop searching deeper, start searching *wider over better data*. Build *simple* alphas on *uncrowded, high-value* fields, then polish lightly. Your instinct and your friend's pattern are both correct — this doc turns them into a concrete, scorable selection rule.
</callout>
## ✅ Confirmed from the live API
<callout icon="📡" color="green_bg">
	A probe run against the BRAIN API verified the exact schema we score on — no guessing.
</callout>
- **Value score + history are dataset-level.** `/data-sets` exposes `valueScore`, `coverage`, `dateCoverage`, `userCount`, `fieldCount`. So we **join each field to its parent dataset** to pull value + history.
- **Per-field metrics** come from `/data-fields`: `coverage`, `type` (`MATRIX` / `VECTOR`), `alphaCount` (crowding), `userCount`, and the parent `dataset` id.
- **Catalog size: 8,155 fields**, offset pagination confirmed working.
- **Scale note:** the dataset `valueScore` uses a different scale than the 1–7 UI cards (e.g. `analyst4` returns `1.0`), so we **min-max normalize** value within the harvested set rather than trust the raw number.
- **Live proof of the thesis:** `abnormal_return_earnings_release` (dataset `model77`) is `MATRIX`, **coverage 0.9992**, but only **202 alphas** — exactly the uncrowded + high-coverage profile we're hunting.
## The core bet (and why it holds up)
Your friend's winner — `group_neutralize(rank(ts_step(absolute_average_announcement_percent_move)), subindustry)` — is not winning because it is clever. It wins because:
- It sits on a **niche event field** (announcement move) that few people have mined.
- It uses a **dead-simple transform** (rank → neutralize), so it has almost no overfitting surface.
- An uncrowded signal has **low correlation** to everyone else's alphas, which is exactly what the platform rewards.
The edge is the **data**, not the math. WorldQuant's own guidance echoes this: *"quality through simplicity,"* few parameters, avoid overfitting. Our current engine does the opposite — it does a *deep* genetic search over a *shallow, crowded* field set (mostly price/volume + fundamentals), which is the lowest-value, most-arbitraged corner of the platform.
## What the "Value Score" actually means
Close, but worth tightening. The value score is WorldQuant's **category-level rating of how valuable that data family is to their research** — higher means they reward alphas there more and it feeds the platform's diversity/"pyramid" incentives. So a high value score *does* mean "they want good alphas here."
But — and this matters — **value score is not the same as uncrowdedness.** A high-value category (e.g. Model) can still be heavily fished. So value score is **one input, not the whole answer.** We combine it with crowding, coverage, and field type.
## The signals we actually have per field
The Data Explorer gives us exactly five usable columns per field. Here's how to read each:
<table fit-page-width="true" header-row="true">
<tr>
<td>Signal</td>
<td>What it is</td>
<td>What we want</td>
<td>Why</td>
</tr>
<tr>
<td>**Value score** (category)</td>
<td>WQ's rating of the data family</td>
<td>High</td>
<td>More rewarded + "wanted"</td>
</tr>
<tr>
<td>**Alpha count** (per field)</td>
<td>How many alphas already built on it</td>
<td>Low (but not \~0)</td>
<td>Low = uncrowded = our edge; \~0 can mean dead/untradeable</td>
</tr>
<tr>
<td>**Coverage %**</td>
<td>Share of the universe with data each day</td>
<td>High (≥ 60–70%)</td>
<td>Applies to more names → stabler Sharpe, easier to trade</td>
</tr>
<tr>
<td>**Date coverage %**</td>
<td>How far back the history goes</td>
<td>High</td>
<td>Long history = trustworthy backtest, less overfit luck</td>
</tr>
<tr>
<td>**Type** (Matrix / Vector / Group)</td>
<td>Shape of the data</td>
<td>Matrix</td>
<td>Matrix = one value per stock per day → drop straight into a simple template. Vector needs aggregation ops first; Group is for neutralization, not a raw signal</td>
</tr>
</table>
## A concrete field-priority score
This is the rule that replaces guesswork. Score every harvested field, rank, and seed from the top down:
```javascript
PriorityScore(field) =
    0.30 * Value        # category value score, normalized 0..1
  + 0.25 * (1 - Crowd)  # 1 - normalized alpha-count  -> uncrowdedness
  + 0.20 * Coverage     # daily universe coverage, 0..1
  + 0.15 * History      # date coverage, 0..1
  + 0.10 * Simplicity   # Matrix=1.0, Vector=0.4, Group=0.0

Hard filters (drop the field before scoring if it fails):
  - Coverage   >= 0.60
  - AlphaCount >  0           # avoid totally dead / untradeable fields
  - Type usable as a signal   # Matrix, or Vector + an aggregation op
```
Weights are a starting point — tune them once we see the real distribution. The key idea: **value + uncrowdedness do most of the work; coverage and history keep us out of fragile backtests; simplicity keeps the seed template trivial.**
> Nuance on alpha count: it's a *noisy* crowding proxy. Very high = arbitraged away. Near-zero is *not* automatically great — it can mean the field is broken, illiquid, or signal-less. The sweet spot is **low-but-nonzero.** {color="gray"}
## Reading your screenshot — which categories to attack
<table fit-page-width="true" header-row="true">
<tr>
<td>Category</td>
<td>Value</td>
<td>Fields</td>
<td>Verdict</td>
<td>Why</td>
</tr>
<tr color="green_bg">
<td>**Sentiment**</td>
<td>7</td>
<td>20</td>
<td>**Attack**</td>
<td>Top value, tiny field set — we can cover *all 20* fast. Watch coverage %</td>
</tr>
<tr color="green_bg">
<td>**Option**</td>
<td>6</td>
<td>138</td>
<td>**Attack**</td>
<td>High value, niche, underused by beginners (IV, skew). Filter hard on coverage</td>
</tr>
<tr color="green_bg">
<td>**Earnings**</td>
<td>5</td>
<td>375</td>
<td>**Attack**</td>
<td>Event-driven; your friend's winner lives here. Simple transforms shine</td>
</tr>
<tr color="green_bg">
<td>**Analyst**</td>
<td>4</td>
<td>1374</td>
<td>**Attack**</td>
<td>Classic simple-alpha turf (revision ranks). Huge set → uncrowded corners exist</td>
</tr>
<tr color="yellow_bg">
<td>**Model**</td>
<td>7</td>
<td>3434</td>
<td>**Selective**</td>
<td>Highest value but composite/pre-modeled fields are often crowded & overlapping. Take only low-alpha-count + high-coverage ones</td>
</tr>
<tr color="yellow_bg">
<td>**Fundamental**</td>
<td>4</td>
<td>1758</td>
<td>**Selective**</td>
<td>Heavily crowded. Only the niche, low-alpha-count fields</td>
</tr>
<tr color="yellow_bg">
<td>**News**</td>
<td>3</td>
<td>1021</td>
<td>**Selective**</td>
<td>Event-driven but noisy. Demand high coverage</td>
</tr>
<tr color="red_bg">
<td>**Price Volume**</td>
<td>2</td>
<td>202</td>
<td>**Avoid (for seeding)**</td>
<td>Lowest value + most arbitraged. This is where the engine currently over-fishes</td>
</tr>
<tr color="red_bg">
<td>**Social Media**</td>
<td>2</td>
<td>22</td>
<td>**Skip**</td>
<td>Low value, tiny set</td>
</tr>
</table>
The pattern is clear: **shift the seed pool away from Price Volume / Fundamental and toward Sentiment, Option, Earnings, Analyst, and curated Model fields.**
## The pipeline: wide → simple → light polish
1. **Harvest** the full field catalog (name, description, type, coverage, date coverage, alpha count, dataset, category).
2. **Filter + score** every field with the PriorityScore above; rank descending.
3. **Seed breadth-first:** one *simple* template per top-ranked field (`rank`, `zscore`, `ts_delta`, `ts_rank` → `group_neutralize`). One alpha per field, spread across many fields — not many alphas on one field.
4. **Test & keep survivors** through the existing qualification + correlation gates.
5. **Polish lightly** with genetics — *settings-first* (neutralization, decay, universe, truncation), not structural complexification.
## How to get the data — use the API, not HTML scraping
Don't scrape the website HTML (fragile, and a ToS grey area). The Data Explorer is backed by BRAIN's **official data-fields / data-sets API** — the same endpoints the page itself calls. It returns the exact columns you listed (field id, description, type, coverage, alpha count, dataset, region) as clean JSON, paginated, filterable by region / delay / universe.
We're already authenticated to BRAIN in the engine, so the right move is to **confirm the endpoint's parameters first** (a small probe), then page through every dataset and dump to a local `data_fields.json` catalog. That catalog becomes the input to the scoring step. **No field names should be invented** — everything comes from the live catalog.
## Honest caveats
- **Survivorship:** "first 20 alphas were submittable" almost certainly includes luck and selective memory. Breadth-first on better data raises the *base hit rate* — it is not a guarantee of instant winners.
- **Value score ≠ uncrowded.** High value can still be crowded; that's why crowding is a separate term.
- **Coverage trap:** the most exotic niche fields often have low coverage. The ≥60% filter is non-negotiable or backtests get fragile.
- **Genetics caution:** complexifying a simple winner usually *raises* turnover and correlation and *lowers* fitness. Keep the genetic stage as light polish, not a rebuild.
## Next steps
- [ ] Confirm the BRAIN data-fields API parameters with a small probe.
- [ ] Harvest the full field catalog → `data_fields.json`.
- [ ] Implement the PriorityScore ranker and review the top \~200 fields together.
- [ ] Rebuild the seed field pool around the top categories (Sentiment / Option / Earnings / Analyst / curated Model).
- [ ] Wire breadth-first simple seeding (one alpha per top field).
- [ ] Dial genetics down to settings-first polish.
## Ranker v2 — refinements after the first run
The first full run surfaced a category bias: the top 25 were all pre-computed `Model` factors with \~1 alpha each. **Decision: do not go Model-heavy.** Four corrections are now live in the ranker:
- **Down-weight Model (×0.6).** Composite factor outputs are pre-derived signals; a simple transform adds little and risks high correlation with the model itself and with everyone else's alphas. Low alpha count on a finished factor is a mirage, not an edge.
- **Sweet-spot crowding, not "lower is always better."** A field with \~1 alpha is *unproven*, not uncrowded gold. The maturity score peaks for low-but-validated fields and decays for crowded ones.
- **Keep sparse data, tag it for ****`ts_backfill`****.** Low coverage no longer disqualifies a field — event/sentiment data is naturally sparse (this is why Sentiment, value score 7, collapsed to 5 fields in v1). Such fields are tagged `coverageMode: "backfill"` so the seeder wraps them in `ts_backfill(...)`. Caveat: backfill fixes *temporal* gaps between events, not *cross-sectional* gaps where only some names ever have data.
- **Per-category quotas.** Selection takes the top fields from *each* category into a diversified `seed_pool.json`, so no single family floods the pool — which is what the pyramid / Triple-Axis Plan rewards.