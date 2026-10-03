# BrainForge v2 — Quant Research & Generator Safety Upgrade

A second, implemented deep pass over the consultant generator. This is a **source
overlay**, not a GitHub commit, live deployment, or new BRAIN pilot. No platform
requests, authentication, scraping, simulations or alpha submissions ran.

## What is new

- Syntax-preserving executable identity and literal provenance; no algebraic
  reassociation or operand/control sorting during canonicalization.
- Durable candidate/attempt receipts and immutable events, known-job recovery,
  ambiguous/expired-job quarantine, bounded retry/deadline behavior, and accepted
  trial-counter repair. Local journaling does **not** imply exactly-once remote execution.
- Configurable atomic per-campaign lifetime dispatch budgets and persistent poll
  operation bounds. `FORGE2_MAX_DISPATCHES=0` means no inferred lifetime quota.
- AST call/depth/field/window resource budgets before simulation dispatch.
- Measured-basket diversity with raw correlation/subspace checks, Ledoit-Wolf
  conditioning, full quadratic replication residual, dataset caps and explicitly
  unverified exploration. It uses standardized PnL intervals, **not capital weights**.
- HAC Sharpe/paired-difference uncertainty, synchronized studentized paired block
  bootstrap, and bounded fixed-pool CSCV. These are offline diagnostics, **not
  automatically substituted into live fitness or selection-adjusted confidence**.
- Forward folds with separated feature warmup and outcome gap, event-aware as-of
  purging, immutable registration, and final-observation exposure sealing.
- Explicit normalized-return contract: no quiet conversion of cumulative dollar
  PnL into investment returns. Data/calendar declarations still require truthful sources.
- Default offline transports, fail-closed risk/correlation evidence, safer recorded
  primary-universe preference, and labeled builtin GROUP fallback.

## Contents and baselines

- `src/`: cumulative v2 source overlay. Keep unrelated repo files.
- `brainforge-v1-to-v2.patch`: applies to the **first implemented release**.
- `brainforge-notion-to-v2.patch`: applies to the **original retrieved Notion mirror**.
- `MANIFEST.json`: both baseline hashes, v2 hashes and validation receipts.
- `tests/`: network-blocked regression/integration suite.
- `research/full-upgrade-report-v2.md`: full lead-quant report and implementation map.
- `research/quant-primary-sources-v2.md`: 11 primary-source recommendations/caveats.
- Independent reviews, resolution notes and evidence live alongside those files.

Do not blindly apply either patch to GitHub main or a live checkout. That source
was not proven identical to these baselines. Back up source, DBs, checkpoints,
epochs, bandit files and attempt ledgers; run `git apply --check` against the right
baseline. This ZIP is not a directory replacement or an instruction to start a
remote campaign.

## Offline verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-offline.txt
PYTHON=.venv/bin/python CATALOG=/path/to/brain_fields_merged.json \
  bash scripts/verify_offline.sh
```

The recorded catalog is unchanged from the first release and remains historical
and partial. It is attached on the release page; its hash is in `MANIFEST.json`.
Default real transports are blocked even for standalone scouting/submission
scripts. Recorded response fixtures are explicitly marked local. No credentials
are needed for verification.

## Reuse existing data, no new pilots

```bash
PYTHONPATH=src .venv/bin/python src/forge2_quant_review.py \
  --db /path/to/existing/brain_memory.db --out quant-review.json
```

Database inputs are read-only. Rows are separated by region/delay/universe;
unknown axes are scoped to their source archive. The report assesses **search
basket redundancy**, not current platform readiness or realized capital returns.
Missing PnL/common overlap retains the original ranking with an explicit
unverified-coverage reason.

For an already recorded normalized return panel:

```bash
PYTHONPATH=src .venv/bin/python src/forge2_quant_review.py \
  --returns /path/to/normalized-panel.json --compare ALPHA_A ALPHA_B \
  --test-size 60 --cscv-blocks 4 --out return-diagnostics.json
```

Panel schema:

```json
{
  "metadata": {
    "unit": "daily_arithmetic_excess_return",
    "calendar": "trading_day",
    "capital_normalization": "verified",
    "cost_basis": "net",
    "excess_return_reference": "documented_cash_rate_or_zero_excess_convention",
    "previously_viewed": true
  },
  "observations": [
    {"date": "2020-01-02", "values": {"ALPHA_A": 0.001, "ALPHA_B": -0.0002}}
  ]
}
```

Supply enough complete chronological observations. The one-row example is only
schema, not a runnable inference sample. `capital_normalization: verified` is a
caller/source attestation, **not verification created by this tool**. Full CSCV
requires an even number of equal blocks and refuses silent row trimming. Declare
fold/block controls before examining results, not to obtain an attractive PBO.
Development diagnostics never compute performance from the final holdout values.
They cannot undo future information used to discover the recorded candidate pool.

`forge2_protocol.register_protocol` defaults to `previously_viewed=True`.
Untouched-holdout claims require an explicit stable exposure namespace. Keep that
namespace stable across file re-encodings, candidate/policy changes and overlapping
registrations, and use one shared seal DB. The seal is workflow discipline, not
access control or proof that source data was never seen elsewhere.

## Existing campaigns and operational evidence

Use the offline migration interface from v1 to copy/rescore into a **new empty**
destination. v2 has a different source/policy fingerprint; do not mix stale scores
silently. Original expressions are preserved as historically executed; the new
canonicalizer does not reverse earlier transformations or recover missing raw data.

Preserve `brain_memory.db.experiments.sqlite` alongside DB/checkpoint/epoch files.
A `dispatching` attempt without a receipt is indeterminate. An
`expired_unresolved` job is not an alpha failure. Do not delete those states or
blindly POST again. Reconciliation methods require an already recorded poll receipt
or completed alpha ID plus a reason; no live reconciliation/probing occurred here.
Shared observed trial counts are repaired idempotently from durable acceptances.

## Synthetic validation, not financial evidence

The report includes CI-coverage sensitivity on 800 stationary Gaussian AR(1)
paths (200 per coefficient, 600 observations each). The strong-dependence case
exposes finite-sample undercoverage even for HAC. This is a useful limitation,
not proof of calibrated probabilities or alpha profitability.

Reproduce in a new raw directory, never overwrite the original evidence:

```bash
PYTHONPATH=src FORGE2_RAW_DIR=/path/to/new-raw-directory \
  .venv/bin/python evidence/coverage_validation.py
```

The script uses the installed data profiler when available in the agent computer;
the release includes the profile receipt, CI endpoint CSV and numerical evidence.
Outside that environment, use the deterministic generation/inference code and
validate the declared `(phi, seed, observation)` grain yourself.

See the full report for formulas, scope, resolved counterexamples, deferred
fold-local discovery/portfolio-weighting work, and honest adoption boundaries.
