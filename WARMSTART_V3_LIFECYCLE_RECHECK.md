# Warmstart v3 — original fixes confirmed; one lifecycle blocker

## Verified outcome

- Uploaded ZIP integrity passed and full revised orchestrator.py is present.
- Original bounded publication, core-rejected-clone, and modified-population import cases are addressed by revised source and supplied tests.
- Independently reran the released offline suite with the uploaded orchestrator.py, forge2_warmstart.py and test_warmstart.py overlaid in an isolated checkout: 146 passed in 13.86 seconds (Python 3.13 offline environment).
- Supplied v3 artifact file digest matches receipt: 18ca966831a49aae0d79646e03c2944fc2e45f379a6f6a74d041a7505ff11786.
- Canonical compact-JSON manifest digest matches internal field and receipt: 70e08853c168904761a3e45ad66f283c9f683b7eefdc74ed9f6d2a9a65be01de.
- validate_warmstart_import accepts the unchanged actual artifact with its matching receipt.
- No platform calls, source edits, original DB/checkpoint writes or live runs occurred. The real campaign DB remains unavailable for independent quant recalculation.

## P1 — evolving checkpoints are mistaken for fresh warmstart imports

Locations: uploaded orchestrator.py _save_checkpoint around lines 939–944, _restore_checkpoint around lines 980–997; forge2_warmstart.py validate_warmstart_import around lines 351–365 and 373–405.

_save_checkpoint keeps the original warmstart_manifest beside the evolving population. _restore_checkpoint invokes validate_warmstart_import whenever that manifest exists, not only when reading the original immutable warmstart artifact. The validator then requires current population triples to equal the ORIGINAL warmstart members exactly.

Normal genetic evolution changes expression, decay, membership and ordering. Such a saved checkpoint is valid evolving state, not tampering with the immutable warmstart. The current restore routing rejects it.

### Reproduced on copies of the actual v3 artifact

1. Import v3 artifact and its receipt into a new AlphaFactory fixture without transport/DB initialization.
2. Populate engine state from the accepted triples.
3. Change one member's decay from 0 to 5 as a valid example of evolving population state.
4. Save to a separate temporary runtime checkpoint using _save_checkpoint.
5. Restart another fixture from that checkpoint.

Result: ValueError: Warmstart population at index 0 does not match manifest member. No source artifact was altered; the population change occurred only in the evolving runtime state before its normal save.

The supplied round-trip test checks saved JSON and tampered ORIGINAL artifact rejection, but never restarts from the newly saved checkpoint after a population change.

## Same lifecycle defect — immutable artifact hash drifts after restart

With no population change, save and restart succeeds. However, validate_warmstart_import hashes the new runtime checkpoint, and _restore_checkpoint assigns that hash to warmstart_file_hash. The immutable origin reference becomes the hash of the mutable checkpoint instead of remaining the original v3 artifact digest.

The fixture reproduced this without altering the population. The next checkpoint save would persist the replacement origin hash, losing the intended chain of provenance.

## Required focused fix

Separate two contracts explicitly:

1. Immutable warmstart artifact import:
   - recognized by explicit artifact schema/type;
   - validate original receipt, canonical manifest, member identities/population equality and declared context before modifying resume state;
   - retain the original artifact SHA-256 and frozen manifest as immutable provenance.

2. Mutable engine checkpoint restore:
   - recognized by a distinct runtime-checkpoint schema/type;
   - validate its current population snapshot, generation/pending state and execution context under the normal checkpoint contract;
   - verify/preserve the warmstart reference independently;
   - do NOT compare an evolved population against initial warmstart membership;
   - keep checkpoint digest and warmstart artifact digest in separate fields.

Do NOT rewrite the historical warmstart manifest on each generation to force equality. Do NOT delete provenance or disable original-artifact tamper checks. Decide explicitly how previously generated checkpoints carrying a warmstart_manifest are handled; do not silently misclassify them.

## Acceptance tests to add

- Original v3 import -> save -> restore -> save -> restore with unchanged population: immutable artifact hash and frozen manifest remain stable.
- Original import -> valid changed population -> save -> restart: current population, generation and decision/random state recover exactly; origin provenance remains unchanged.
- Mid-generation checkpoint with pending offspring and a compatible epoch restores through the runtime route.
- Altered ORIGINAL artifact/receipt/manifest is still rejected, before any engine decision-state mutation.
- Invalid runtime checkpoint/context still fails closed; the distinction must not turn off ordinary checkpoint validation.

## CLI instruction

Fix only the warmstart-versus-runtime-checkpoint routing and immutable origin reference. Preserve existing artifacts, active checkpoints and databases. Add the real restart tests above, rerun the offline suite, and return the complete changed source/tests plus logs. No new BRAIN pilots, authentication, simulations, submissions, state overwrites or pushes.

## Reproduction harness

The attached script tests only temporary copies of the uploaded artifact and new temporary checkpoints:

```bash
FORGE2_OFFLINE_ONLY=1 python checkpoint_lifecycle.py --src /path/to/isolated/src --artifact /path/to/evidence_aware_warmstart_v3.json --out lifecycle-results.json
```

It asserts the observed regression, not desired fixed behavior. Use it to design acceptance regressions rather than preserving its defect assertions after the fix.
