# Independent bounded v2 review — current parent fixes rechecked

Read-only review of `/data/brainforge-v2/src` against `baseline`. No source/test changes, real network/BRAIN requests, secrets or other agents. Synthetic reproductions used temporary databases and the existing `RecordedNetwork` fixture. Real socket/curl request methods were blocked in engine reproductions. This report is the only intentional project-file write.

**Final current-source suite:** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests -p no:cacheprovider`: **120 passed in 5.71s**. Initial pre-interim suite had 114 passes; those earlier results/findings are not substituted for the current checks. Whole-tree discovery initially encountered baseline/src smoke-test module-name collision; scoped `tests` avoids that unrelated collection problem.

Parent's interim fixes were reread and the remaining findings below were reproduced against the updated files. Names/function anchors are preferable to line numbers while the parent is editing concurrently.

## Remaining concrete findings

### P1 — New registration resets one-shot holdout consumption through the same API

**Anchors:** `forge2_protocol.register_protocol`, `HoldoutSeal.evaluate`.

Seal consumption is keyed only by `protocol_hash`. `created_at` is included in the registration hash, so registering the exact same plan/data/policy again creates a fresh key and permits another evaluation in the **same seal DB**. This is an API-level bypass, not the acknowledged limitation that someone can read data outside the API.

**Current executed repro:** in a temporary directory d, dates are 750 consecutive ISO dates:

```python
plan = forward_folds(dates)
seal = HoldoutSeal(d/'seal.sqlite')
for i in range(2):
    registration = register_protocol(d/f'p{i}.json', plan,
                                     'SAME_DATA', 'SAME_POLICY')
    print(seal.evaluate(registration, 'SAME_CANDIDATE', 'SAME_DATA',
                        lambda interval: True))
```

Output: **True, True**. Both registrations default to `previously_viewed=False`.

**Risk/fix:** timestamps, filenames, candidates and policy versions must not restore untouched observations. Keep consumption identity separate from registration identity: a shared exposure key for data/holdout observations, with explicitly recorded reused/development-only evaluation when appropriate. Caller-supplied hashes still need truthful artifact verification. Retain the existing protection that a crash leaves one registration claimed.

**Regression:** re-register identical final data in a second file, same seal DB, then a changed candidate/policy: repeated untouched evaluation must fail or explicitly be classified reused.

### P2 — Correct residual formula still admits exact blends under strong shrinkage

**Anchors:** `forge2_portfolio.residual_fraction`, `select_basket` conditional novelty gate.

The parent's full raw-covariance quadratic residual formula is now mathematically correct for the chosen shrunk-ridge coefficients. **The old ridge-Schur formula bug is resolved.** However, strong shrinkage makes replication coefficients nearly zero. The resulting large residual measures an underfit replicator, not absence of a raw-panel linear dependency. Exact blends still appear almost entirely novel.

**Current deterministic repro:**

```python
rng = np.random.default_rng(6)
x, y, z = rng.normal(size=(3, 100))
columns = {'a': x, 'b': y, 'blend': x+y}
columns.update({f'noise{i}': rng.normal(size=100) for i in range(100)})
# 100 consecutive ISO dates; series[k]=dict(zip(dates,cumsum(columns[k]))).
# rows ordered as columns, expression=rank(k), universe=U;
# metadata[k]={'dataset':k,'type':'MATRIX'}.
selected, report = select_basket(rows, series, metadata, 3,
    explore_fraction=0, max_dataset_fraction=1,
    min_residual_fraction=.15, max_abs_correlation=.8)
```

Output: **a, b, blend**. Shrinkage **0.9577578537896868**; blend's reported verified residual fraction **0.9357594365657327**. Raw centered blend is exactly the sum of a and b, with zero empirical replication residual to numerical tolerance. Pairwise correlations stay below .8.

**Risk/fix:** a high-p candidate set can make known multi-signal redundancy pass the gate. Add an explicitly tolerance-controlled raw-panel subspace/replication check alongside the regularized predictive residual; label the latter as regularized replication error, not unqualified empirical novelty. Keep shrinkage for conditioning. This is an underfitting/interpretation issue, not a remaining error in the new quadratic formula.

**Regression:** exact blend with p>T/high shrinkage must not earn verified new linear signal. Existing small-p/500-observation blend test is insufficient.

### P2 — Exploration candidates are not compared with previous exploration selections

**Anchor:** `forge2_portfolio.select_basket` exploration loop.

`ids` is updated for the measured core but not when exploration adds an evidence-covered candidate. Subsequent exploration candidates are checked only against the core. Exploration can therefore contain known duplicate/sign-flip pairs, contradicting its “never includes a known duplicate” comment.

**Current executed repro:** same RNG, 100-date/cumulative-sum construction as above, ordered `a=x, b=y, flip_b=-y, c=z`, all distinct datasets:

```python
selected, report = select_basket(rows, series, metadata, 4,
    explore_fraction=.75, max_dataset_fraction=1)
```

Output: **a, b, flip_b, c**; exploration **b, flip_b, c**; rejections **{}**. All have 99 aligned intervals, so this is not missing evidence. The same defect applies at the default exploration fraction when its reserve has at least two slots.

**Fix/regression:** compare against all already selected evidence-covered candidates and update selected indices on exploration insertion. Test duplicates/sign flips located inside the reserve, not only core duplicates.

### P2 — Duplicate pending entries double-score recovered completed evidence

**Anchors:** `orchestrator.AlphaFactory._evaluate_population`, recovery-key dedup bypass and population/history append.

A key in `_recover_pending_keys` bypasses `evaluated_canon` for every occurrence, rather than once per batch. Original offspring are checkpointed before normal evaluation deduplicates them, so repeated proposals can legitimately exist in a pending checkpoint. Completed evidence then produces duplicate population/history records without another remote evaluation.

**Current executed genuine checkpoint repro:** using `tests/test_engine_integration.py::engine_setup` and its recorded adapter:

```python
f = build_factory(meta)
await f.run(generations=1)
f.generation = 1
child = {'expression':'rank(f1 + f2)', 'universe':'U', 'decay':0}
f._save_checkpoint(pending_offspring=[child, child])
await f._evaluate_population([child], allow_grid=False)
await f.shutdown()
g = build_factory(meta)
await g.initialize()
await g._bootstrap_population()
g._recover_pending_keys = {'rank(f1 + f2)|U|0'}
out = await g._evaluate_population([child, child], allow_grid=False)
```

Output: **2 returned records, 2 matching population entries, zero recorded-adapter network calls**.

An earlier defensive repeat of an already scored `rank(f1)` with its recovery key enabled changed fitness **1.9916207010042577 → 0.15613886249025463**, adding population/history copies while only one original POST occurred: it was scored again against changed elite context including itself. That numeric case predates the parent's interim changes, so it is supporting context, not a new-current score assertion. The current duplicate checkpoint repro above was rerun after the fixes.

**Important negative check:** a normal single-child pending checkpoint independently preserved fitness **1.0845500880582073** and qualification True/True with no recorded calls before the interim updates. Do not generalize this finding into “every resume drifts.”

**Fix/regression:** unique per-batch evaluation identities even under recovery; idempotent merge/replace rather than append for already enriched evidence. Assert population/history cardinality and fitness on duplicate checkpoint entries and repeated recovery, not only that a child exists and no POST was made.

### P2 — Persistent poll deadlines do not bound a request's internal throttling loop

**Anchors:** `forge2_experiments.reserve_poll`; `orchestrator._simulate_alpha` awaited GET; `network_engine.NetworkEngine.request` 429 branch.

The parent now persists acceptance deadlines and poll-operation counts, and expires unresolved work rather than recording a loser. **The earlier reset-deadline/timeout-as-loser findings are resolved.** Remaining issue: deadline/operation checks happen before an awaited request. Its 429 branch retries indefinitely; capped backoff duration is not a retry or elapsed-time cap. One reserved poll can issue unbounded internal HTTP attempts and hold the semaphore beyond its deadline without reaching another `reserve_poll` check. Simulation POSTs receiving repeated 429s have the same unbounded internal throttling behavior.

**Current offline executed repro:** `NetworkEngine.__new__`, fake rate limiter with immediate `wait/defer`, fake session always returning status 429 and `Retry-After: 0`; no actual session/network is created. Wrap `obj.request('GET','/job/fixture')` in `asyncio.wait_for(..., timeout=.005)`.

Output: external timeout after **266 fake request calls**. Only the external `wait_for` terminated it. This count is timing-dependent, not an asserted stable constant; absence of an internal bound is the finding.

**Fix/regression:** propagate the persistent remaining deadline into bounded network awaits/retry loops and cap internal attempts/elapsed time. Count HTTP operations, not only calls to the wrapper, if claiming that operational budget. Fake-clock/fake-429 tests should terminate within their registered bound without an unrelated caller timeout. Preserve expired-unresolved/no-repost state.

### P2 — Event-aware as-of check skips test-event feature availability

**Anchor:** `forge2_protocol.purge_forward_events`.

The new function validates interval ordering and checks feature availability for candidate training rows. But it immediately skips every test index before the `feature_available_at > decision_time` check. Validation events using features unavailable at their own decision time are accepted without any exclusion/error. Future feature leakage invalidates held-forward scoring even when training labels are perfectly purged.

**Current executed repro:**

```python
events = [
 {'decision_time':'2020-01-01', 'outcome_start':'2020-01-01',
  'outcome_end':'2020-01-01', 'label_available_at':'2020-01-01',
  'feature_available_at':'2020-01-01'},
 {'decision_time':'2020-01-02', 'outcome_start':'2020-01-02',
  'outcome_end':'2020-01-02', 'label_available_at':'2020-01-03',
  'feature_available_at':'2020-01-03'}]
purge_forward_events(events, [1])
```

Returns **train_indices=[0], test_indices=[1], excluded={}**. Test event 1's feature arrives a day after its decision.

**Fix/regression:** require causal feature availability on test rows too, before accepting their validation membership; reject or explicitly mark unusable validation observations. Outcome/label availability after a test decision is normal and should not itself be rejected. Tests must distinguish future features from legitimate future outcomes.

## Parent fixes confirmed / no new bug claim

- Syntax-only executable canonicalization now preserves grouping/order and literal lexemes. Rerun of `rank((1e16 + -1e16) + 1)` emits `rank(1e16 + -1e16 + 1)` and retains value **1.0**. Safe identity also includes NUMBER/STRING lexemes. The earlier reassociation/rounding-collision finding is **withdrawn for current files**.
- Raw residual quadratic expression is corrected; remaining high-shrinkage blend behavior above is a narrower issue.
- Absolute accepted-job deadlines, expired-unresolved quarantine and transactional configurable lifetime dispatch counts are now present. Accepted handle commits precede shared trial accounting. No exactly-once remote atomicity claim is made.
- Source context/scoring lineage is separated more carefully; this review does not assert that a scoring-policy change must force a new remote evaluation.
- `forge2_quant_review` refuses inference on raw archive PnL and requires explicit capital-normalized daily-excess-return metadata. Archive basket diagnostics are labeled standardized PnL, not capital weights. No silent unit conversion reproduced. Metadata is still a declaration, not independent proof of normalization/calendar.
- HAC influence/Bartlett formula is correct for its stated conditional asymptotic scope. Percentile moving-block bootstrap accurately names its approximate, selection-unadjusted output; absence of studentization is a narrower implemented scope, not falsely presented as bootstrap-t.
- Development diagnostics do not use holdout performance values. Feature warmup is now separate from label horizon. General interval purging has its own explicit event API; the test-feature issue above is within that API, not an objection to the documented simpler splitter.
- Known receipt GET recovery, ambiguous transport/5xx no blind POST retry, remote-complete detail recovery, completed-ledger recovery after derived DB failure, and outside-host receipt rejection remain covered by passing tests. Preserve them.
- Old OOS winner-rank diagnostic is explicitly renamed/described as not PBO; no current PBO overclaim reported.

## Suggested next fixes

1. Holdout exposure identity and pending replay idempotence.
2. Actual request/deadline bounds and test-event causal features.
3. Raw subspace redundancy alongside regularized replication, and exploration-to-exploration duplicate checks.

All regressions can use existing synthetic/recorded adapters. No new pilot, network evidence, or profitability claim is necessary.
