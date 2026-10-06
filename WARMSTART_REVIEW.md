# Evidence-aware warmstart review — not accepted for activation

## Scope and verdict

Reviewed the 11 supplied files in BrainForge_Artifacts_latest.zip, especially build_evidence_warmstart.py and evidence_aware_warmstart.json. The archive contains no regression test modules and no updated shared selector or restore implementation. Offline fixtures imported the uploaded builder against the previously released v2 modules in /data/brainforge-v2/src. No BRAIN calls, credentials, real campaign DBs, or source edits were used.

The supplied JSON is internally consistent with a 20-member population, 16 measured-core records and four exploration records. This does not independently verify its PnL calculations: the source campaign DB and field metadata were not included. Do not replace an active checkpoint with this artifact yet.

Six fixture counterexamples reproduced across five finding categories; results are recorded in repro-results.json. These are counterexamples, not a production acceptance suite.

## 1. P1 — output may destroy source state

Location: build_evidence_warmstart.py lines 46–49, 182.

The guard rejects only a resolved basename of checkpoint.json. It does not refuse an existing destination, a path equal to db_path or meta_path, or the released engine's actual default checkpoint filename .wq_checkpoint.json. atomic_json replaces its target; SQLite mode=ro only protects the read connection, not a later filesystem replacement.

Fixture 1: using the temporary source.db as --out replaced its SQLite bytes with JSON. Fixture 2: an existing .wq_checkpoint.json marker was overwritten. No real DB/checkpoint was used.

Fix: default to create-only publication; reject existing outputs and source-path aliases, including symlink resolution/samefile checks. Enforce destination ownership and a race-safe no-clobber publication primitive rather than exists() followed by os.replace(). Preserve output/source hashes as test evidence. This can be builder-specific; do not change the shared state writer's legitimate replacement semantics globally.

## 2. P1 — check-row presence is mislabeled verified qualification evidence

Location: lines 119–122.

has_checks and aid in checks_data is treated as CHECKS_VERIFIED without parsing metrics_json. A row containing not-valid-json was promoted to CHECKS_VERIFIED in the fixture. Empty, NULL, unknown-result, failed and pending payloads are not interpreted either. This is an evidence-label defect; the review did not establish that it actually submits an alpha or bypasses an engine gate.

Fix: decode and parse the raw payload using the shared check evidence parser. Preserve verified evidence separately from failed/pending/unknown results. Verification of the payload is not current platform qualification. Missing/malformed evidence must remain unverifiable, and the historical freshness/provenance boundary must stay explicit.

## 3. P2 — deduplication uses raw expression rather than evaluation identity

Location: lines 78–84.

The builder drops distinct decay configurations when expression strings match. Conversely, rank(f) and rank( f ) survive as separate rows with identical settings. A three-row fixture yielded two output members with one evaluation identity; the different-decay evaluation was dropped.

Fix: use semantics-preserving expression identity plus full evaluation settings and explicit source/epoch/operator/catalog context. Do not apply algebraic rewrites or merge control settings. Export that identity per member. If settings were never recorded, preserve that uncertainty instead of inventing verified full payloads.

## 4. P2 — no-evidence fallback can exceed the declared exploration quota

Location: lines 94–104 and 138–147, interacting with select_basket's insufficient_common_evidence fallback.

The shared selector intentionally retains base ranking when common evidence is inadequate. The builder then labels every selected row unverified_exploration, without enforcing its own reserve ceiling. In a size=5, explore_fraction=0.2 fixture, two no-PnL candidates were exported despite a one-member reserve.

Fix: establish a measured-core pool explicitly and select it with exploration disabled. Only admit the declared number of independent, attributed exploration identities afterward. If evidence is insufficient, underfill honestly or refuse per declared policy. Do not change the shared evolutionary selector's fallback accidentally just to repair this builder.

Dataset membership is only an attribution predicate. It does not prove a signal is nonconstant or economically meaningful; keep those unknown for unmeasured exploration. An expression such as subtract(f,f) contains a field but can still be degenerate.

## 5. P2 — provenance is incomplete and lost on the released restore/save path

Location: builder lines 156–178; released orchestrator.py _restore_checkpoint and _save_checkpoint.

The artifact omits input hashes, metadata hash/path, policy/epoch/operator/catalog hashes, max_dataset_fraction, max_abs_correlation, min_residual_fraction, min_overlap and ridge. Its assumed-axis caveat is useful but is not a compatibility contract.

An isolated AlphaFactory.__new__ fixture restored the population keys successfully, but did not retain warmstart_manifest. The next _save_checkpoint removed the manifest. Triple-list compatibility alone does not implement a validated warmstart importer or guarantee that all rows match the destination DB's evaluation keys.

Fix: define a versioned warmstart import contract. Validate identities, policy/settings/epoch compatibility and tier counts, verify available input hashes, retain assumptions, and record the immutable warmstart file hash in checkpoints. Preserve the full sidecar manifest independently. Test both restore and subsequent save in an isolated campaign with network transports prohibited.

## Additional audit/report corrections

- daily_changes constructs matched cumulative-PnL intervals and excludes intervals longer than four calendar days. Report 1,234 matched intervals, not 1,234 verified trading days. The artifacts do not export the exact excluded intervals explaining the previous 1,236-date inventory. Add raw-point, differenced, gap-excluded and final common-interval counts plus the excluded boundaries/reasons.
- pnl_covered_ablation.py line 250 supplies a hardcoded 1234 fallback for missing common_intervals_T. Remove that fallback: unavailable interval evidence must stay unavailable.
- Existing 136-test evidence predates this helper and does not certify it. No new builder regression tests or full isolated restore receipt were supplied in this ZIP.
- Snapshot/input hash records are needed to reproduce results; the real PnL covariance and basket metrics were not independently recomputed here.

## Required acceptance tests

1. Existing output and both input-path aliases rejected without changing bytes; .wq_checkpoint.json protected; symlink and concurrent-output cases covered.
2. Missing, malformed, failed, pending, unknown and valid check payloads preserve their distinct evidence states.
3. Whitespace variants collapse only under identical evaluation context; distinct decay/settings remain distinct.
4. No/short/non-overlapping/flat PnL cannot enter measured core or inflate exploration quota; underfill is explicit.
5. Core and exploration identities are disjoint, attribution is checked, inputs are finite and sorting deterministic.
6. Full selection controls and input/context provenance are serialized; unavailable history remains an assumption.
7. Source DB and existing checkpoint hashes remain unchanged; output is deterministic for fixed inputs.
8. Isolated restore preserves membership and warmstart provenance through the next checkpoint save, without any POST/GET/auth call.

## Recommended CLI task

Fix these bounded warmstart acceptance findings with tests. Keep original sources, DBs and active checkpoints intact; publish to a new create-only artifact. Run the existing 136-test offline suite plus the new builder/import tests, and return source changes, receipts and the resulting warmstart JSON. Do not enable live mode, authenticate, backfill remotely, simulate, submit, overwrite production state or push.

## Reproducing these fixture findings

Use the offline verification environment and the released v2 modules. This harness asserts the observed defects, not the desired fixed behavior; convert them to acceptance regressions when implementing fixes.

```bash
FORGE2_OFFLINE_ONLY=1 python reproduce_review.py --src /path/to/src --builder /path/to/build_evidence_warmstart.py --out repro-results.json
```
