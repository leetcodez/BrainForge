# V2 review resolution — targeted read-only recheck

Bounded recheck of current `/data/brainforge-v2/src` after the parent's six fixes. No source/test edits, BRAIN requests, real network calls or other agents. Only this report was written intentionally in the project. Engine boundary reproductions used the existing `RecordedNetwork` fixture with real socket/curl request functions blocked.

## Outcome

**132 tests passed in 6.69s** with:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests -p no:cacheprovider
```

All six previous concrete counterexamples are addressed in the current implementation and targeted regression coverage. No remaining P1 defect was established in this bounded pass. There is one concrete P2 recovery-accounting defect and a narrower exposure-namespace assurance boundary worth tightening before making strong claims.

## Previous findings: resolution

| Previous issue | Current mechanism checked | Narrow assurance |
|---|---|---|
| Registration timestamp/policy/candidate resets final holdout | Exposure table keyed by namespace + each holdout date; claim and seal in one transaction; defaults `previously_viewed=True` | Re-registration and overlapping holdout dates cannot reset exposure **within the same exposure namespace and seal DB**. Crash leaves exposure consumed. |
| High-shrinkage exact blend called novel | Raw-panel least-squares subspace fraction checked before regularized quadratic residual | Exact blends are rejected at the declared numerical tolerance even in the tested p>T/high-shrinkage panel. This is empirical sample-span redundancy, not an independent-factor estimate. |
| Exploration admits internal sign flips | Evidence-covered exploration candidates append to selected indices | Later exploration checks include earlier evidence-covered selections. Unknown evidence remains explicitly unverified. |
| Duplicate/repeated pending recovery double-scores | Per-batch `seen_batch`; keys already in population skipped | The duplicate pending-checkpoint regression merges once; repeat recovery noops without changing population/history or making recorded transport calls. |
| Internal 429 retries escape bounds | Total attempts + monotonic request deadline; bounded session/rate/auth awaits; poll request wrapped with remaining accepted-job deadline | The fake-429 regression terminates internally at its configured attempt cap. Persistent accepted deadline bounds the outer poll request; no blind POST recovery. This does not guarantee remote cancellation. |
| Test events accept unavailable future features | Explicit test-index feature-as-of validation before training purge | Future validation features raise; later test outcomes/labels remain permitted. Timestamp truthfulness and complete feature lineage are still caller obligations. |

Also reread syntax-only canonicalization and lexeme-preserving identity: the prior floating reassociation defect remains fixed. Warmup/outcome horizon separation is explicit. Primary universe is chosen from recorded availability/preferences; builtin GROUP keys are kept distinct from recorded custom-group provenance. No new defect in those changes was established by this targeted pass.

## Remaining P2 — accepted receipt recovery does not repair shared hypothesis accounting

**Anchors:** `orchestrator.AlphaFactory._simulate_alpha`, accepted/remote-complete/completed branches; `forge2_trials.TrialLedger.record`.

The accepted handle is correctly committed **before** the shared trial-counter update. That protects recovery from a counter-write crash, but creates a necessary replay obligation. The shared `trial_ledger.record(...)` call currently occurs only after a fresh POST response. Recovering an already accepted/remote-complete/completed attempt does not execute it. Therefore a crash between accepted-handle commit and shared-counter commit leaves a known accepted hypothesis absent from the shared observed count.

### Executed offline crash-window reproduction

Using the existing engine fixture, attach a fresh shared `TrialLedger`, set `trial_context='USA_d1'`, and create a durable accepted receipt without recording the shared hypothesis—exactly the state a crash between those two commits leaves:

```python
f = build_factory(meta)
await f.initialize()
f.trial_ledger = TrialLedger(temp_dir/'shared_trials.db')
f.trial_context = 'USA_d1'
payload = config.build_simulation_payload('rank(f1)', 'U', 0)
a = f.experiment_ledger.prepare(payload, f.experiment_context)
f.experiment_ledger.dispatch(a['attempt_id'])
f.experiment_ledger.accept(a['attempt_id'],
    config.WQ_BASE_URL+'/job/prepaid', time.time()+100)
result = await f._simulate_alpha('rank(f1)', 'U', 0)
print(result.valid, f.trial_ledger.count(),
      f.experiment_ledger.summary()['states'], f.network.calls)
```

Observed:

```
True
0
{'completed': 1}
[('GET', '/job/prepaid'), ('GET', '/alphas/prepaid')]
```

Remote recovery is correct and POST-free; shared accounting is not repaired. New-factory history import may repair a basic expression/universe/decay row on a *later* restart once derived data exists, but does not fix the current shared count before scoring, nor necessarily restore every distinct full payload. The count feeds the engine's multiplicity heuristic; undercounting can weaken its penalty. This is not a claim that the counter estimates independent N or that the existing DSR is a profitability probability.

**Suggested fix/regression:** idempotently replay shared hypothesis/full-payload recording from every durable known-accepted-or-later receipt, using the original payload and campaign context. Keep the accepted-handle-first order. Inject a shared-counter failure immediately after receipt acceptance, restart, recover by GET only, and assert the exact original payload appears once in shared accounting before enrichment/scoring. Local dispatch budgets are separately durable and are not shown broken by this repro.

## Exposure namespace boundary — artifact re-encoding can still reset the default scope

**Anchors:** `register_protocol` default `data_exposure_namespace or data_hash`; `HoldoutSeal` exposure key.

The original same-data-hash re-registration bug is resolved. Protection across data versions depends on callers reusing a **stable source/history exposure namespace**, not an artifact hash that changes when the file is re-encoded, extended or gains columns. The new regression explicitly supplies a stable namespace for re-encoded data; that is the right mechanism. However the API default is the changing artifact hash, so this protection is not automatic.

**Executed boundary repro:** same plan, dates, frozen candidate and seal DB, but registrations use `data_hash='DATA_VERSION_1'` and then `'DATA_VERSION_2'`, each explicitly asserting `previously_viewed=False` and omitting the optional exposure namespace. Both evaluations return True. Same underlying final observations in differently encoded artifacts would have this shape. With the same stable exposure namespace, the second is correctly rejected.

This is a **conditional assurance gap**, not an assertion that the API can identify arbitrary dishonest source metadata. A different legitimate source may deserve a different namespace. Still, treating artifact version hashes as the default history namespace makes an accidental exposure reset easy.

**Suggested tightening:** require an explicit stable exposure namespace for any untouched-final evaluation, or document/refuse cross-version assurance under the artifact-hash fallback. Bind source identity and observation IDs deliberately; retain artifact hash separately for byte/version provenance. A shared exposure registry cannot police copies to another seal DB, renamed source namespaces, or accesses outside the API.

## Honest assurance boundaries

- This pass establishes local regression behavior, not real-platform integration correctness, future profitability, independent strategy count, or complete discovery-validation separation.
- Capital-normalized excess-return inference requires truthful explicit units/calendar/cost/capital metadata; archive PnL remains separately labeled. No silent unit conversion was found.
- HAC intervals remain asymptotic, conditional fixed-strategy diagnostics. Percentile moving-block bootstrap remains approximate and selection-unadjusted. Shrinkage/subspace metrics are in-sample search controls, not investable weights or proof of independent bets.
- Forward purging relies on complete causal feature/outcome timestamps; it cannot retroactively remove globally selected candidate-pool leakage.
- Durable local receipts do not create atomic remote exactly-once submission. Ambiguous and expired jobs remain unresolved unless reconciled from known evidence. Bounded local polling does not cancel a remotely accepted job.
- Current repeat-recovery guards preserve existing enriched population evidence; they are not a general promise that re-scoring under a deliberately different policy must give identical scores.

**Recommendation:** repair shared-count replay; enforce/document stable exposure namespaces. The six original counterexamples need no further pilots or remote calls to close.
