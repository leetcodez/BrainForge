# Warmstart v2 recheck — fixes confirmed, three acceptance gaps remain

## What was verified

- Revised uploaded archive extracts safely and passes ZIP integrity.
- evidence_aware_warmstart_v2.json matches the receipt's file SHA-256: 0a305e3e6b5f4d9180e9a5ea0680aa05da6a2532c6431750959ca5c3ecc68fcf.
- Its internal manifest digest matches the companion receipt: 5119cbc68f8a824324d5990bdd140f5ea778514e81e064e2fae0b673805c013c. The 5e4c... manifest digest in the chat summary is not the supplied artifact's digest; use the actual matching receipt.
- Artifact tier counts are internally consistent: 16 core plus 4 exploration, population 20.
- Uploaded checks parser correctly distinguishes missing/malformed/failed/pending/historical-pass states in the supplied tests.
- Output guards, expression whitespace/decay deduplication, no-PnL exploration quota and source immutability tests pass.

## Dependency/testing scope

The archive does NOT contain the revised orchestrator.py. Initially, seven new tests passed and the restore test failed against the unchanged released engine, as expected. Applying precisely the user-pasted hashlib + restore/save metadata-preservation diff to an isolated copy of released dependencies produced 144 passing tests. The source upload itself was not edited. Runtime here was the prior offline Python 3.13 environment, not the reported local Python 3.12 environment.

No original database, local backup directory, epoch input metadata or full current checkout was supplied, so real campaign selection metrics and local backup preservation remain outside independent verification. No network calls were made.

## Remaining finding 1 — P1: concurrent publication can publish the wrong payload

Location: forge2_warmstart.py lines 127–151.

The temporary filename is .tmp.<target-name>.<pid>, and tmp.write_text is not exclusive. Two threads in one process targeting the same output therefore share and overwrite the same temporary file.

A bounded, deterministic fixture orders these events:
1. Publisher A writes its payload to the shared temp and pauses.
2. Publisher B overwrites that temp with B's payload.
3. Publisher A links the temp to the destination and returns success.
4. Publisher B fails with FileExistsError.

Result: A successfully publishes B's content, and returns the hash of B's artifact. The main destination was not overwritten, but caller/payload integrity was violated.

Fix: use securely allocated unique temporary files (mkstemp/O_EXCL), serialize with allow_nan=False, fsync the completed temporary file, then use a no-clobber publication primitive and fsync the containing directory. Do not claim atomic publication for the open(target, 'x') fallback: readers/crashes can observe an incomplete file while it is being written. On unsupported filesystems fail explicitly or implement a tested appropriate protocol.

Add concurrent writer and crash/fallback tests. These tests must assert the successful publisher's file bytes match that publisher's intended payload, not merely that only one target exists.

## Remaining finding 2 — P2: measured-rejected clones return as exploration

Location: forge2_warmstart.py lines 412–444.

The exploration loop skips core identities and unattributed fields, but ignores basket_report['rejections'] and does not enforce known correlation/residual or combined dataset-budget constraints.

Fixture: three distinct expression identities, with A and B having identical nonflat PnL and C an independent synthetic series. Size=3, reserve=1. Core selects A/C and explicitly rejects B for absolute_return_redundancy. Exploration then selects B. B is a measured clone, not unknown diversity.

Fix: distinguish unknown diversity from already observed redundancy. Keep known-rejected clones/sign flips/subspace failures out of exploration; enforce declared whole-basket dataset constraints consistently. If there are insufficient admissible exploration candidates, underfill. Do not claim an unmeasured attributed expression is non-degenerate.

Add regressions for known pairwise clone, sign flip, raw-subspace rejection, dataset cap and unknown-PnL reserve behavior.

## Remaining finding 3 — P2: restore preserves provenance but does not validate the import contract

Location: the user-pasted orchestrator.py _restore_checkpoint diff and forge2_warmstart.py.

The added restore code stores warmstart_manifest and computes/copies a file digest, but it does not verify schema, receipt expectations, manifest digest, population-to-member equality, tier identities/counts or expected destination policy/context.

Fixture: alter one population decay to 5 while leaving all manifest identities and the original receipt unchanged. The stated restore implementation accepts and restores that altered decay. Computing a fresh digest of the current file is not a comparison against the expected published artifact.

Fix: add an explicit validated import function and call it before mutating engine resume state. Check the trusted expected artifact digest/receipt, recompute the manifest digest, verify exact population/member correspondence, distinct identities/tier quotas, and declared compatibility with the destination epoch/policy/operator/catalog/settings. Preserve unavailable historical settings/axes as assumptions rather than claiming verified full evaluation context.

The uploaded evaluation identity only includes universe/decay and source/assumed region/delay. It does not currently include the other execution settings or catalog/operator/epoch context. The actual artifact's epoch_id is null, and no scoring-policy compatibility hash is supplied. Decide and test an explicit compatible research-import policy rather than bypassing guards or fabricating historical provenance. epoch_manifest_path is accepted by the builder but currently unused.

Add rejection tests for modified population, bad manifest/receipt hash, schema/count mismatch and incompatible destination context, plus a valid restore/save round trip retaining the immutable artifact reference.

## Acceptance-test caveat

The supplied disjointness test constructs linear cumulative PnL: increments for both covered candidates are constant. The selector therefore has no nonflat measured core, so an empty core identity set can satisfy isdisjoint() vacuously. Add an assertion that the intended measured-core fixture really produces core members, using nonflat independent increments.

The test named serialized_controls_and_gap_diagnostics only calls audit_series_intervals; it does not assert full control serialization or import-context validation. Extend it accordingly.

## Next bounded task

Fix only these three acceptance categories and the test fixture gaps. Preserve the existing v2 artifact and all live checkpoints/databases; publish a new artifact. Return forge2_warmstart.py, complete revised orchestrator.py, revised tests, receipt and test log. Keep offline mode and no remote execution. The acceptance target is trustworthy publication + evidence-aware selection + validated restore, not an additional generator redesign.

## Reproduction

The attached harness asserts observed counterexamples, not desired fixed behavior. Run in the offline environment against an isolated src directory containing the revised warmstart module and stated restore/save diff:

```bash
FORGE2_OFFLINE_ONLY=1 python recheck_counterexamples.py --src /path/to/isolated/src --out counterexample-results.json
```

All destructive-write scenarios use temporary fixtures; the harness does not use actual campaign databases or active checkpoints.
