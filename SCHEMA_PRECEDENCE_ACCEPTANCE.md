# Lifecycle acceptance and minimal schema-precedence fix

## Verified

The uploaded source now fixes evolving-population restart and immutable origin-hash preservation. Its complete 151-test suite passes independently against the released offline dependencies (Python 3.13), including the new lifecycle tests. The original v3 artifact/manifest digests match its receipt. No real campaign DB, active checkpoint, user source file or platform state was modified.

## One bounded routing bypass found

_restore_checkpoint currently lets the presence of population_snapshot, decision_state, or pending_offspring classify a file as a legacy runtime checkpoint even when schema_version explicitly says forge2-warmstart-v1.

Using temporary copies of the original v3 artifact and original receipt, changing a population decay is correctly rejected normally. Adding any one of these presence-only markers separately bypasses that validation:

- population_snapshot: null
- decision_state: {}
- pending_offspring: []

All three changed artifact copies were accepted and restored the modified decay. The explicit conflict check catches checkpoint_type=runtime_checkpoint plus warmstart schema, but did not catch the heuristic legacy markers.

## Minimal fix supplied

warmstart-schema-precedence.patch adds four lines: an explicit warmstart schema takes precedence over presence-only legacy runtime heuristics. Existing explicit conflicting markers are still rejected; the genuine runtime route remains unchanged. No speculative generator or scoring changes are included.

Three parameterized regression cases verify that these markers cannot route an explicit artifact away from import validation and that rejection happens before warmstart/population resume state is assigned.

## Independent results

- Uploaded suite: 151 passed in 3.74s.
- Patched suite with three new cases: 154 passed in 3.97s.
- git apply --check: passed against the uploaded orchestrator.py baseline.
- Applied patch source matches the tested copy byte-for-byte.
- Original artifact digest remains 18ca966831a49aae0d79646e03c2944fc2e45f379a6f6a74d041a7505ff11786.
- No platform calls, real DB/checkpoint writes, credential access, pushes or deployment.

These are bounded offline acceptance results, not a production security audit or proof of financial efficacy. Backup/commit claims on the user's machine were not independently inspected.

## Apply to the local checkout

1. Compare src/orchestrator.py against the original source hash in patch-source-hashes.json. If it differs, inspect the local diff rather than overwriting current work.
2. Keep the existing Git checkpoint/backups and v3 artifact.
3. Check/apply the narrow patch from the repo root:

```bash
git apply --check /path/to/warmstart-schema-precedence.patch
git apply /path/to/warmstart-schema-precedence.patch
```

4. Copy tests/test_warmstart_schema_precedence.py into the repository's tests directory. It uses the supplied evidence/evidence_aware_warmstart_v3.json plus its receipt.
5. With FORGE2_OFFLINE_ONLY=1, run the full suite. Expect the three new cases in addition to the existing suite.
6. Refresh the release manifest and record a reviewed local Git checkpoint; no automatic push or live activation.

After that, freeze the warmstart/import lifecycle as an offline research baseline. The next project step is recorded-evidence evaluation under fixed controls, not another warmstart rewrite or new BRAIN pilot.
