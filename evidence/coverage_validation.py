"""Synthetic, fixed-strategy CI coverage sensitivity. Not BRAIN evidence."""
from pathlib import Path
import json
import os
import subprocess
import numpy as np
import pandas as pd
from forge2_inference import sharpe_inference

root = Path(__file__).resolve().parents[1]
raw_dir = Path(os.getenv("FORGE2_RAW_DIR", str(root / "evidence/raw")))
raw_dir.mkdir(parents=True, exist_ok=True)
target = 0.05
n = 600
repetitions = 200
phis = [-0.5, 0.0, 0.5, 0.8]
raw_rows = []
results = []
for scenario, phi in enumerate(phis):
    sigma = 0.01 / np.sqrt(1 - phi * phi)
    for repetition in range(repetitions):
        seed = 20261002 + scenario * 10000 + repetition
        innovations = np.random.default_rng(seed).normal(0, 0.01, n + 500)
        process = np.zeros(n + 500)
        for t in range(1, len(process)):
            process[t] = phi * process[t - 1] + innovations[t]
        returns = process[500:] + target * sigma
        raw_rows.extend((phi, seed, t, float(value))
                        for t, value in enumerate(returns))
        for method, lag in [("IID", 0), ("HAC auto", None), ("HAC 20", 20)]:
            estimate = sharpe_inference(returns, lags=lag)
            low, high = estimate["daily_interval"]
            results.append((phi, seed, method, estimate["lags"], low, high,
                            bool(low <= target <= high)))

raw_path = raw_dir / "synthetic_daily_returns.csv"
if raw_path.exists():
    raise RuntimeError("Raw fixture is immutable; remove/rename intentionally to regenerate")
pd.DataFrame(raw_rows, columns=["phi", "seed", "observation", "return"]).to_csv(raw_path, index=False)
profiler=Path('/skills/data-analysis/scripts/profile_data.py')
with (root/'evidence/coverage_profile.txt').open('w') as profile:
    if profiler.exists():subprocess.run(['python3',str(profiler),str(raw_path)],stdout=profile,stderr=subprocess.STDOUT,check=True)
    else:profile.write('Bundled profiler unavailable; deterministic declared-grain/null/duplicate checks run below.\n')
loaded=pd.read_csv(raw_path)
assert len(loaded)==len(phis)*repetitions*n and not loaded.isna().any().any()
assert not loaded.duplicated(['phi','seed','observation']).any()
details = pd.DataFrame(results, columns=["phi", "seed", "method", "lags", "low", "high", "covered"])
details_path = root / "evidence/coverage_replicates.csv"
details.to_csv(details_path, index=False)
summaries = []
for phi in phis:
    for method in ["IID", "HAC auto", "HAC 20"]:
        subset = details[(details.phi == phi) & (details.method == method)]
        successes = int(subset.covered.sum())
        summaries.append({"phi": phi, "method": method, "covered": successes,
                          "replicates": len(subset), "coverage_percent": 100 * successes / len(subset)})

# Independent headline reconciliation from serialized interval endpoints, not
# the computed Boolean column or grouped aggregation above.
persisted = pd.read_csv(details_path)
for row in summaries:
    cells = persisted[(persisted["phi"] == row["phi"]) & (persisted["method"] == row["method"])]
    direct = sum(float(lo) <= target <= float(hi) for lo, hi in zip(cells.low, cells.high))
    assert direct == row["covered"] and len(cells) == row["replicates"]

evidence = {
    "source": "synthetic stationary Gaussian AR(1), not platform or strategy-performance evidence",
    "daily_true_sharpe": target, "observations_per_replication": n,
    "burn_in": 500, "replicates_per_scenario": repetitions,
    "confidence": 0.95, "summary": summaries,
    "raw_file": str(raw_path),
    "independent_interval_check": "passed",
    "assumptions": [
        "Fixed process and fixed method settings declared before generation; no model/alpha selection.",
        "HAC auto follows the implemented bandwidth rule; 20 lags is a predeclared sensitivity, not an optimized calibration.",
        "Coverage is the fraction of 200 simulated intervals containing the known daily Sharpe; finite Monte Carlo uncertainty remains.",
        "This does not validate BRAIN profitability, heavy-tail/regime robustness, or selection-adjusted inference.",
    ],
    "comparison_plan": [
        {"grain": "method x AR coefficient", "population": "200 complete independent synthetic paths per coefficient",
         "unit": "percent interval coverage", "derivation": "covered / complete replications * 100",
         "finding": "Serial dependence exposes finite-sample bandwidth and IID-assumption limits.",
         "disposition": "chart", "reason": "Grouped coverage rates reveal different uncertainty behavior on identical paths."},
        {"grain": "individual simulation", "population": "same paths",
         "unit": "daily Sharpe CI endpoints", "disposition": "file",
         "reason": "Audit detail, not a second visual finding."},
    ],
}
(root / "evidence/coverage_evidence.json").write_text(json.dumps(evidence, indent=2))

spec = {
    "version": 1, "form": "categorical-bars", "layout": "report",
    "title": "Serial dependence exposes uncertainty-model limits",
    "aside": "Synthetic AR(1); 200 paths per case, 600 observations each. Coverage = intervals containing true daily Sharpe. Nominal 95%; not BRAIN results.",
    "orientation": "vertical", "mode": "grouped",
    "labels": [f"AR φ = {phi:g}" for phi in phis],
    "axis": {"zero": True, "cap": 100, "referenceLine": {"value": 95, "label": "Nominal 95%"}},
    "derived": True, "derivationReason": "Intervals containing known true daily Sharpe divided by all 200 complete replications.",
    "series": [
        {"label": method, "valueKind": "percent", "role": role,
         "data": [next(r["coverage_percent"] for r in summaries if r["phi"] == phi and r["method"] == method)
                  for phi in phis]}
        for method, role in [("IID", "base"), ("HAC auto", "subject"), ("HAC 20", "aux")]
    ],
}
(root / "evidence/coverage_chart.json").write_text(json.dumps(spec, indent=2))
print(json.dumps({"summary": summaries, "independent_interval_check": "passed"}, indent=2))