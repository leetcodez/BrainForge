## Executive conclusion
**The next upgrade should make BrainForge a safer, auditable research system—not simply a larger generator.** This second pass implements that direction on top of the first consultant-generator release: executable-semantic preservation, durable paid-attempt accounting, bounded resource use, measured basket redundancy controls, dependence-aware offline inference and disciplined forward/holdout evaluation.
The deliverable is implemented source, two baseline-specific patches, tests, primary-source research and reproducible evidence. It is **not** a GitHub commit, live deployment, new BRAIN pilot, new platform scrape, alpha submission, or proof of improved earnings. No real platform request or authentication was performed. The first release remains preserved as the v1 baseline; its recorded catalog remains historical and partial.
### The main decisions
1. Keep the evolutionary/NSGA-II engine, but fix executable identity and evidence before changing its economic reward.
2. Add basket-aware research selection using observed aligned PnL, with unknown coverage explicitly unverified—not treated as independence.
3. Add conditional HAC/bootstrap and fixed-pool CSCV diagnostics, but **do not** substitute them automatically into fitness or pretend they correct adaptive discovery.
4. Make real transports offline by default. Reuse existing archives and normalized return evidence; do not demand another live pilot.
The v1 implementation and September handoff define the architectural context. The updated source is a versioned overlay, not an assertion that GitHub main or every historical Notion file has changed.[\[1\]](https://app.notion.com/p/30e900b2367f4d4093317a95a0e16d05)[\[2\]](https://app.notion.com/p/3d1ba36ddc9480d78cb8cb215b3cd43f)
## 1. What a deeper review found
The first release corrected important vocabulary, availability, learning and resume issues. That did not establish mathematical or operational completeness. This pass found additional defects at more consequential seams:
- The old canonicalizer sorted/reassociated additions, multiplications and selected function arguments. Floating-point reassociation can change execution, and positional controls must not move. A whitespace cache key is not permission to perform real-number algebra on a proprietary DSL.
- A successful remote simulation could lose its response or local receipt, while transport/5xx retry logic automatically POSTed again. Local state cannot infer that the first request was never accepted.
- A failed/malformed self-correlation response could become zero correlation. Missing risk metrics could become zero drawdown/margin. Those are missing observations, not passes.
- Pairwise correlations alone miss a candidate that is a blend of several existing signals. Shrinkage can make an underfit replicator appear to leave novel residual variance—even when the raw panel contains an exact dependency.
- A simple sample gap does not know feature publication times or outcome-information intervals. A new registration hash does not make already exposed holdout dates untouched again.
- The old “approximate PBO” was an IS-winner OOS-rank statistic from one split, not combinatorially symmetric cross-validation.
An independent read-only review reproduced six further counterexamples after the new tests initially passed. They were addressed with regressions. A follow-up review found an accepted-receipt/shared-counter crash gap; replay now repairs that counter idempotently. Review files are retained as historical evidence rather than rewritten into a misleading clean bill of health.
## 2. Prioritized upgrade map — implemented vs deferred
<table header-row="true">
<tr>
<td>Priority</td>
<td>Upgrade</td>
<td>Status and exact scope</td>
</tr>
<tr>
<td>P0</td>
<td>Preserve executable semantics and full evaluation identity</td>
<td>Integrated: syntax-only formatting, literal lexemes, AST/settings/catalog/operator identity; no algebraic operand reassociation</td>
</tr>
<tr>
<td>P0</td>
<td>Journal paid attempts and quarantine ambiguity</td>
<td>Integrated: durable intent/receipt/terminal events; known jobs recover by GET; unknown acceptance is never blindly reposted</td>
</tr>
<tr>
<td>P0</td>
<td>Bound dispatch/retry/poll resources</td>
<td>Integrated: atomic configurable campaign dispatch budget, persistent poll-operation count/absolute deadline, finite retry and await bounds</td>
</tr>
<tr>
<td>P0</td>
<td>Fail closed on missing risk/correlation evidence</td>
<td>Integrated in engine and relevant reporting parsing; explicit successful empty correlation records remain a legitimate zero</td>
</tr>
<tr>
<td>P0</td>
<td>Separate PnL and investment-return contracts</td>
<td>Integrated in offline review: capital-normalized daily excess-return metadata required for return inference; raw PnL remains interval diagnostics</td>
</tr>
<tr>
<td>P1</td>
<td>Measured basket redundancy and family budgets</td>
<td>Integrated into generation survival, conditional on common evidence; raw point/subspace checks plus regularized residual, dataset caps and declared exploration</td>
</tr>
<tr>
<td>P1</td>
<td>Conditional serial-aware uncertainty</td>
<td>Implemented offline: HAC influence-function CI, paired HAC contrast, moving-block percentile and synchronized paired bootstrap-t</td>
</tr>
<tr>
<td>P1</td>
<td>Causal forward folds and information purging</td>
<td>Implemented offline: warmup vs label gap, event/as-of checks on training and test events; not a retrospective reconstruction of discovery</td>
</tr>
<tr>
<td>P1</td>
<td>Holdout exposure discipline</td>
<td>Implemented: immutable registrations, explicit stable namespace for untouched claims, per-observation exposure and one shared seal DB; not DRM or proof of prior non-exposure</td>
</tr>
<tr>
<td>P1</td>
<td>Correct PBO labeling / bounded actual CSCV</td>
<td>Integrated rename; separate fixed-pool CSCV helper and optional CLI diagnostics, with complete-panel and partition limits</td>
</tr>
<tr>
<td>P1</td>
<td>Respect configured recorded primary universe</td>
<td>Integrated: recorded preference first, explicit override supported, coverage fallback labeled; builtin GROUP constants separate from custom recorded keys</td>
</tr>
<tr>
<td>P2</td>
<td>Full fold-local generator/surrogate/bandit discovery</td>
<td>Deferred: normalized underlying series, causal feature/label evidence and recorded fold-local discovery are not supplied</td>
</tr>
<tr>
<td>P2</td>
<td>Investable portfolio weights, costs and marginal utility</td>
<td>Deferred: capital, cost, exposures and actual portfolio-return evidence are required; search-basket diversification is not capital allocation</td>
</tr>
<tr>
<td>P2</td>
<td>Learned regime adaptation or RL/MCTS replacement</td>
<td>Deferred: no data supports a reliable new economic reward or efficacy claim; foundation first</td>
</tr>
</table>
The new statistical helpers are implemented interfaces, not a claim that the user's actual strategy archive has been calibrated. No historical campaign SQLite DB or verified capital-normalized daily excess-return panel was supplied for this pass.
## 3. Preserve semantics before paying for experiments
### Implemented
`syntax_validator.py` no longer sorts or flattens executable arithmetic or commutative-call arguments. It formats syntax while restoring the original numeric/string literal lexemes. This preserves excess decimal precision that Python's parsed float would otherwise round before emission. `forge2_search.py` combines AST structure with those lexemes and complete payload settings/context for identity.
Regression examples include:
- `(1e16 + -1e16) + 1` evaluates differently from `1e16 + (-1e16 + 1)`; they stay distinct.
- `multiply(z, a, 0)` retains positional order.
- `1.0000000000000001` is not silently emitted as `1.0`.
- `rank(-f)` does not collapse into `-rank(f)`.
- Division by a raw field does not merge with guarded division.
LLVM explicitly distinguishes permission for floating-point reassociation from normal semantics, and protected GP operators illustrate why real-number identities cannot be assumed in a DSL. Those sources justify caution; they do not prove BRAIN's exact missingness, units or execution semantics.[\[3\]](https://llvm.org/docs/LangRef.html#fast-math-flags)[\[4\]](https://gplearn.readthedocs.io/en/latest/intro.html)
### Resource budgets
Preflight now enforces bounded AST nodes, calls, depth, operand symbols and supported lookback roles. Defaults are 160 nodes, 32 calls, depth 18, eight field/group operands and a 1,500-observation supported lookback ceiling. These are engineering limits, not evidence of optimal horizon or platform cost. Unsupported proprietary roles are not claimed fully typed.
Historical expressions are retained **as previously executed**. This release cannot reverse earlier canonicalization or recover raw source text that was never stored. v2 policy migration creates an explicitly new score view, not an invented original history.
## 4. Protect remote work without promising impossible exactly-once execution
`forge2_experiments.py` introduces a per-campaign SQLite candidate/attempt ledger with immutable events and transactional transitions:
```javascript
prepared → dispatching → accepted(receipt, absolute deadline)
         → remote_complete(alpha ID) → completed(raw result/metrics)
```
`failed` means an explicitly known rejection/remote failure. `dispatching` without a receipt means **indeterminate acceptance**. `expired_unresolved` means the local deadline/resource bound closed while remote work remains unresolved. Neither unknown state is manufactured into an alpha failure or a refunded opportunity to repost.
### Integrated protections
- Persist intent before POST; persist an observed acceptance handle before shared trial accounting or further awaits.
- Resume an accepted handle by bounded GET polling; resume remote completion by detail GET; replay a completed ledger result into a missing derived DB without network.
- Reject outside-host polling receipts rather than forwarding credentials.
- Refuse automatic simulation POST retry after transport errors or 5xx ambiguity.
- Enforce finite internal retry count/wall deadline and bound rate/session/auth waits. Original accepted-job remaining time also bounds the outer poll await.
- Maintain persistent poll-operation counts. This counts wrapper operations; internal HTTP attempts have a separate per-request cap, not a falsely claimed unified global count.
- Reserve optional lifetime dispatch capacity atomically across concurrent attempts in the same campaign DB. Zero disables the inferred lifetime quota; a cap is not a provider-verified account allowance.
- Repair the separate shared observed-trial counter from durable accepted/completed receipts on replay. Missing counter writes no longer suppress observed search exposure.
- Preserve the attempt ledger with DB/checkpoint/epoch backups. Reconciliation accepts **already recorded** handles/alpha IDs plus reasons; no new live reconciliation was conducted.
RFC 9110 cautions against automatic retries of non-idempotent requests without known idempotency or evidence that the original was never applied. SQLite provides local transaction primitives, but neither source establishes platform-specific deduplication or an atomic transaction spanning remote acceptance and local commit.[\[5\]](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)[\[6\]](https://sqlite.org/lang_transaction.html)
**Unavoidable limit:** if remote acceptance happens before the response/local receipt is lost, local journaling cannot prove whether it happened. This release promises conservative local accounting and no blind repost—not exactly-once remote execution. It uses one stored attempt per evaluation identity; automatic terminal retries are not an implemented workflow.
## 5. Upgrade basket selection without manufacturing diversification
`forge2_portfolio.py` and the engine's generation-survival seam now assess an evidence-covered primary-regime basket. Region/delay/universe regimes are not quietly mixed. The offline reviewer scopes unknown axes to their own archive.
### Data construction
- Difference cumulative PnL only on exactly matched `(start, end)` intervals; arbitrary end-date matches and missing pairs do not become zero correlation.
- Fit on a declared common complete interval panel, not pairwise-stitched covariance entries.
- Standardize observed columns for research redundancy. The resulting weights/coefficients are not capital weights.
- Use Ledoit–Wolf identity-target covariance shrinkage for conditioning, with its actual shrinkage coefficient recorded.
Ledoit–Wolf and sklearn document the identity-target estimator. Numerical conditioning is not evidence of independent economic signals, and iid shrinkage theory is not serial-aware inference.[\[7\]](http://ledoit.net/Well-conditioned2004.pdf)[\[8\]](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html)
### Redundancy controls
1. Raw absolute correlation rejects observed duplicate/sign-flip dimensions.
2. Raw least-squares subspace residual detects exact **and near** blends of already selected components, including a high-dimensional/high-shrinkage case.
3. Shrunk-ridge replication coefficients are assessed using the **full raw-covariance quadratic residual**:
$$
V_e = 1 - 2b^T c_{raw} + b^T R_{raw}b
$$
This is not the ridge Schur-complement shortcut. Injected identity covariance is not rewarded as measured novelty.
1. Every non-GROUP dataset used by a mixed expression consumes its dataset budget, rather than arbitrarily attributing it to one dominant field.
2. Evidence-covered exploration selections enter the comparison set too; reserve candidates cannot include a known duplicate/sign-flip of an earlier reserve choice.
When common evidence is insufficient, the original ranking is retained with an explicit **diversity unverified** reason. When evidence is adequate, constraints can intentionally underfill the population rather than refill it with known redundant components. Platform eligibility remains a separate gate.
**Boundary:** negative correlation can be useful in a capital portfolio. Here a sign flip is the same signal dimension, so it is not counted as novel alpha reach. This module does not optimize net portfolio utility, transaction costs or investable weights. Its fitted covariance/residuals are in-sample; they do not establish future diversification or independent trials.
## 6. Add mathematically appropriate uncertainty—but keep it conditional
### HAC Sharpe uncertainty
For explicit daily arithmetic excess returns, the implementation uses the mean/variance delta-method influence series:
$$
\psi_t = \frac{r_t-\mu}{\sigma} - \frac{S}{2}\left(\frac{(r_t-\mu)^2}{\sigma^2}-1\right)
$$
with Bartlett/Newey–West long-run variance:
$$
\Omega = \gamma_0 + 2\sum_{k=1}^{L}\left(1-\frac{k}{L+1}\right)\gamma_k,\qquad SE(S)=\sqrt{\Omega/T}.
$$
HAC of returns alone would estimate mean uncertainty, not full Sharpe uncertainty. The influence-function implementation is independently cross-checked against the equivalent moment-gradient calculation. Paired contrasts use the **difference of aligned influence series**, preserving cross-strategy covariance rather than adding unrelated standard errors.[\[9\]](https://www.nber.org/papers/t0055)[\[10\]](http://www.ledoit.net/jef_2008pdf.pdf)
The report keeps daily Sharpe, conditional CI, and conventional square-root annualization **scaling proxy** separate. Under serial dependence, the conventional scaling is not asserted to be exact horizon Sharpe. Lo's publisher abstract was available; the full article was not retrieved, and no unverifiable equation-number quotation is used.[\[11\]](https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios)
### Block bootstrap
Single-series output is explicitly an approximate overlapping moving-block **percentile** interval. Paired output uses shared sampled row indices and **studentized bootstrap-t** Sharpe differences. Clones stay clones; block construction does not independently resample components or wrap endpoints under an unnamed stationary-bootstrap scheme. Degenerate replicates are counted and excessive degeneracy refuses an interval.[\[12\]](https://projecteuclid.org/journals/annals-of-statistics/volume-17/issue-3/The-Jackknife-and-the-Bootstrap-for-General-Stationary-Observations/10.1214/aos/1176347265.short)[\[13\]](https://www.ssc.wisc.edu/~bhansen/718/Politis%20Romano.pdf)[\[10\]](http://www.ledoit.net/jef_2008pdf.pdf)
**These methods do not correct adaptive alpha selection, solve regime nonstationarity, certify an independent N, or produce a calibrated probability of profit.** Lags/block length, finite moments and weak-dependence/local-stationarity assumptions remain visible. The helpers reject inadequate, flat or nonfinite samples instead of fabricating confidence.
### Synthetic validation exposed a real limitation
A predeclared stationary Gaussian AR(1) experiment generated 800 paths: 200 paths per coefficient, 600 observations each, after 500 burn-in observations. The true daily Sharpe was 0.05. The chart compares nominal 95% CI coverage on the **same paths** under an IID assumption, the implemented automatic HAC bandwidth, and a predeclared 20-lag HAC sensitivity.
For the strongest positive-dependence fixture, φ=0.8:
- IID: **93/200 = 46.5%** coverage.
- HAC automatic lags: **158/200 = 79.0%**.
- HAC 20 lags: **179/200 = 89.5%**.
All three are below the nominal 95% in that fixture. Negative dependence gives a different failure pattern: IID overcoverage. The correct conclusion is **bandwidth/assumption sensitivity**, not “HAC is now calibrated.” These are finite Monte Carlo diagnostics of synthetic stationary processes—not BRAIN data, not alpha returns, and not a live pilot. Endpoint-based independent reconciliation, raw-data profile, per-path CI CSV, complete summary and deterministic generator are included.
<embed src="https://prod-files-secure.s3.us-west-2.amazonaws.com/e27ba36d-dc94-8119-9451-00031cc0d47c/e2e7ab55-d8b3-4fa5-913b-dcb464766f17/uncertainty_coverage_notion_agent_chart.html?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=ASIAZI2LB466TPWUNPGK%2F20261003%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20261003T045820Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjENv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLXdlc3QtMiJHMEUCIFq7IEHCyx%2FUUv2hxEHHof9aeEtVsBZOqAKucGlQspBzAiEAqTIhK5pbGpICDlNSxxsPWejKueTq5XeN1zWx0B8eRB0qiAQIo%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARAAGgw2Mzc0MjMxODM4MDUiDEA978lCx0Q2ixsrWircA6iiq1prm71jKk2eau6%2FCKFwHHTsCKrgBD%2BbTG3AWMeFo944Jn%2BmFqFdvOciRyxGQRVUW7g0Acz%2FHzWn6BWy%2F%2B6djN4NBkFzD41JARRQOO%2FpuQLN46FzSI0XaOkhF0z8BAoE%2Bq7NL24u0bHqt9xuBACPiaVsev%2FmXPFeQnskWPdh%2FHrbSyZ8Z77UAyRstjznHhIbBPKEBkMSds1HeMEbj6PCE9gPE65xjuVYAg%2F3WHDAbe9NnX82oANcAkR4fmj4xbVvKWj1M0bTpjqPqiIatcl6lu%2BV7DVoU9GYtr2Z12oITuW856ckMrsFpqw%2BUaKr1GHZk5AD9YrqXXbbulcfk5UraEr8alqPpmZVTwfd%2BF%2Ftdnf%2BXQEPQZ8xL1b98gsbegOIeWMbh32QcXpTFbxJQIbTGM8MxhdMZY64VN4ejsY0R%2BCLIvAuvzUeO%2BGDjWRoroTQo1S1RO3vAX91b%2F0JDLUpjorl%2B9%2B8j8lg3RbeEH0MobLAIa1y2lL1NPh3HC6CiqKoAxaK8TIiqP%2FOEtZzWbT4G1caqY2PUMTJr0sZEoI3mBZvkDMM3ZWYxEKi%2BiD%2F8hWlub0%2FN8yFaVwe5Z2AAgqhr%2BTsfohvBDiuQAMN2LIH2WInDRk8Hl8be5r2MMXNgdYGOqUBllJng7WLho9ImzRt8zi6bx3JguuoWRj6s8m0FmgrsF9em0HEmCsRlzFz5kG0c42POlMpld4aTUCZupjH7TGFvXAcLMec2FAvgs2Zh8TYlr8o1Tm1a8flcB9CSJ2Ze6Vt%2BVSFwRQMTkVC4%2BHxjC1WosLwjldK3fxhEETP%2FItay1L9rW46QAb4zhgdfZBlUaZ5D7kBsAkOGa9YHjqG%2B4d5nQoozzZW&X-Amz-Signature=4ba5dd3a19a90deefe4ae60193941da593e0cc56c65e34d87077751a61af4554&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject#notion_record=block.efa6fc67-d1b8-4b6f-9955-8a4913f660f5.e27ba36d-dc94-8119-9451-00031cc0d47c"></embed>
## 7. Forward validation cannot undo leaked discovery
`forge2_protocol.py` separates trailing-feature warmup from outcome/label gap. Its event-aware API checks:
- decision precedes validation cutoff;
- training outcome-information intervals do not overlap validation outcome intervals;
- training labels were available before fitting;
- **both training and test features** were available as of their decision timestamps.
Future test outcomes are normal; future test features are leakage. Inclusive interval boundaries and excluded-row reasons are explicit. A strict forward scheme has no future training rows to remove with a post-test embargo; this is not general CPCV.[\[14\]](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)[\[15\]](https://www.quantresearch.org/Innovations.htm)
The CLI evaluates fixed recorded candidates on development test blocks and never computes performance from the final holdout values. It does **not** refit the entire generator, covariance, surrogate, bandit, threshold search or candidate-discovery process separately inside each fold. A candidate pool already selected using full history remains a selected pool; later splitting its scores does not retroactively make discovery out-of-sample.
### Holdout exposure, not timestamp theater
Registrations are immutable and hash data/policy/plan. Unknown history defaults to `previously_viewed=True`. An untouched claim requires an explicit stable exposure namespace, and the shared seal DB records individual exposed holdout dates. Re-registering in another file, changing a candidate/policy, overlapping windows or re-encoding the same data under the same stable namespace does not restore untouched status. A crash after claim remains consumed.
The namespace must remain stable across versions of the same underlying observational data. Source truth, prior exposure elsewhere, caller honesty and external filesystem access cannot be proved by this API. It is research workflow discipline, not cryptographic access control or a claim that the existing archived history is untouched.
## 8. Correct PBO labeling and add bounded fixed-pool CSCV
The old logging path is now **single-split IS-winner OOS-rank diagnostic (not PBO)**. It returns unavailable with inadequate pairs rather than a false zero.
`forge2_cscv.py` separately implements symmetric half-block partitions of a fixed complete synchronized return pool. It selects the IS winner, ranks that same column OOS, forms rank logits, and reports the fraction of negative logits. Equal blocks, finite/nonflat columns, tie policy and a partition budget are enforced; no silent trimming is used. A small case is independently checked by enumeration.[\[16\]](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
This is fixed-pool CSCV—not chronological deployability, all adaptive trials, proof of future profit, or permission to repeatedly inspect the final holdout. No CSCV statistic for the user's real alpha pool is claimed because that pool's complete normalized return matrix was not supplied.
## 9. Safer primary-universe and readiness behavior
The builder now honors a configured preferred universe **when it is recorded for that axis**, supports an explicit recorded override, and labels coverage fallback. Listing breadth alone no longer silently overrides the configured preference.
The saved USA/d1 liquid-axis records did not include usable custom GROUP rows in the current selection. Instead of inventing availability or reverting to an illiquid universe to satisfy a test, the builder uses explicitly labeled builtin GROUP constants and keeps them separate from custom recorded field keys. Actual catalog smoke validation caught and checked this change.
Missing drawdown/margin fails a configured gate. HTTP failures, missing correlation lists, NaN/out-of-range values and malformed rows do not become zero correlation. Only an explicit successful empty record list has the documented zero-correlation interpretation. This improves evidence handling; it does not freshly certify current platform eligibility.
## 10. Validation and reproducibility
The final release evidence records:
- **136 passing network-blocked regression/integration tests.** They cover existing v1 behavior and new mathematical, semantic, exposure, budget, request-bound and recovery cases.
- **10,000 actual GeneticEngine outputs** checked over 5,000 seeded iterations; zero structural invalid outputs and zero network attempts in the stress harness. This is synthetic-metadata syntax/type stress, not economic validation or proof that every output clears every resource budget.
- **54 saved-catalog smoke checks**, zero failures across USA/d1, EUR/d1 and USA/d0; actual loader/subprocess/engine integration has separate regressions.
- **800 synthetic AR(1) paths** for conditional CI sensitivity, with an independent endpoint-based coverage check and explicit finite-sample undercoverage.
- Dual patch applicability checks: first implemented release → v2 and original retrieved Notion Python mirror → v2. Applied source must match the released source byte-for-byte.
- Read-only archive/migration fixtures preserve original database hashes. Known accepted jobs recover without another POST; completed ledger evidence survives derived DB failure; duplicate pending recovery does not duplicate population/history scores.
Independent bounded reviews and parent-resolution notes are included. Their passing suites and narrow rechecks are not an exhaustive production audit or full proprietary DSL proof.
## 11. Execution and adoption — no new pilots required
1. Back up source and preserve DBs, checkpoints, vocabulary epochs, bandit state and attempt ledgers.
2. Choose the matching baseline patch and compare hashes. Do not blindly apply either patch to GitHub main or a different live checkout.
3. Run the offline verifier with the existing recorded catalog. No credentials are needed.
4. Use `forge2_quant_review.py --db ...` for existing archives. It is read-only and reports standardized PnL-basket coverage/redundancy, not return inference or current readiness.
5. Supply an already recorded, documented normalized daily excess-return panel only if available. The contract requires units, capital normalization, cost basis, calendar and excess-return reference. Declarations are not independent proof; unknown sampling/capital must stay unknown.
6. Declare fold/comparison/block controls before looking at results. Keep final observations and their stable exposure namespace sealed. Do not reinterpret a reused archive as fresh holdout data.
7. If a policy differs, use copy/rescore migration into a **new empty directory**, retain its assumptions receipt and old fitness. Do not delete ambiguity records to make the runner proceed.
Real transports default to offline, including standalone scout/submission scripts. This release does not authorize switching that mode, production deployment, new simulations or submission. Integration into the matching checkout and review of existing evidence are the next engineering steps.
## 12. What still needs genuine evidence—not another speculative claim
- Actual capital basis, costs, regular trading sessions, point-in-time features and label/outcome availability.
- Fold-local candidate discovery and train-only fitting across the **whole** adaptive pipeline, not just a fixed-pool score review.
- Forward validation of portfolio replication, net marginal utility and investable constraints; current redundancy selection is in-sample.
- Reliable regime/label feedback and a sufficiently complete qualified-history dataset before training a new surrogate or RL policy.
- Provider-verified idempotency/reconciliation if exactly-once remote acceptance is ever required.
- Verified expression/theme multiplier attribution and current submission readiness, rather than historical metadata proxies.
The second pass is intentionally stronger in engineering and quant discipline without claiming outcomes that the available evidence cannot support.
## Release artifacts
Source overlay, both baseline-specific patches, tests, manifest, research and reproducible synthetic evidence:
<file src="https://prod-files-secure.s3.us-west-2.amazonaws.com/e27ba36d-dc94-8119-9451-00031cc0d47c/d93522ab-7435-4315-b025-1e3a8d046476/brainforge-v2-quant-upgrade.zip?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=ASIAZI2LB466TPWUNPGK%2F20261003%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20261003T045820Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjENv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLXdlc3QtMiJHMEUCIFq7IEHCyx%2FUUv2hxEHHof9aeEtVsBZOqAKucGlQspBzAiEAqTIhK5pbGpICDlNSxxsPWejKueTq5XeN1zWx0B8eRB0qiAQIo%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARAAGgw2Mzc0MjMxODM4MDUiDEA978lCx0Q2ixsrWircA6iiq1prm71jKk2eau6%2FCKFwHHTsCKrgBD%2BbTG3AWMeFo944Jn%2BmFqFdvOciRyxGQRVUW7g0Acz%2FHzWn6BWy%2F%2B6djN4NBkFzD41JARRQOO%2FpuQLN46FzSI0XaOkhF0z8BAoE%2Bq7NL24u0bHqt9xuBACPiaVsev%2FmXPFeQnskWPdh%2FHrbSyZ8Z77UAyRstjznHhIbBPKEBkMSds1HeMEbj6PCE9gPE65xjuVYAg%2F3WHDAbe9NnX82oANcAkR4fmj4xbVvKWj1M0bTpjqPqiIatcl6lu%2BV7DVoU9GYtr2Z12oITuW856ckMrsFpqw%2BUaKr1GHZk5AD9YrqXXbbulcfk5UraEr8alqPpmZVTwfd%2BF%2Ftdnf%2BXQEPQZ8xL1b98gsbegOIeWMbh32QcXpTFbxJQIbTGM8MxhdMZY64VN4ejsY0R%2BCLIvAuvzUeO%2BGDjWRoroTQo1S1RO3vAX91b%2F0JDLUpjorl%2B9%2B8j8lg3RbeEH0MobLAIa1y2lL1NPh3HC6CiqKoAxaK8TIiqP%2FOEtZzWbT4G1caqY2PUMTJr0sZEoI3mBZvkDMM3ZWYxEKi%2BiD%2F8hWlub0%2FN8yFaVwe5Z2AAgqhr%2BTsfohvBDiuQAMN2LIH2WInDRk8Hl8be5r2MMXNgdYGOqUBllJng7WLho9ImzRt8zi6bx3JguuoWRj6s8m0FmgrsF9em0HEmCsRlzFz5kG0c42POlMpld4aTUCZupjH7TGFvXAcLMec2FAvgs2Zh8TYlr8o1Tm1a8flcB9CSJ2Ze6Vt%2BVSFwRQMTkVC4%2BHxjC1WosLwjldK3fxhEETP%2FItay1L9rW46QAb4zhgdfZBlUaZ5D7kBsAkOGa9YHjqG%2B4d5nQoozzZW&X-Amz-Signature=3fad240eaa535833f243bffc7510feb8e543a61977f8a1a17a5308cf39e7ba36&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject#notion_record=block.44775b8a-5e9e-4f6d-a794-3f317b3aad5b.e27ba36d-dc94-8119-9451-00031cc0d47c"></file>
Portable full report:
<file src="https://prod-files-secure.s3.us-west-2.amazonaws.com/e27ba36d-dc94-8119-9451-00031cc0d47c/56001a4c-b04f-4d3b-abdc-bd3cd1757fc6/full-upgrade-report-v2.md?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=ASIAZI2LB466TPWUNPGK%2F20261003%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20261003T045820Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjENv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLXdlc3QtMiJHMEUCIFq7IEHCyx%2FUUv2hxEHHof9aeEtVsBZOqAKucGlQspBzAiEAqTIhK5pbGpICDlNSxxsPWejKueTq5XeN1zWx0B8eRB0qiAQIo%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARAAGgw2Mzc0MjMxODM4MDUiDEA978lCx0Q2ixsrWircA6iiq1prm71jKk2eau6%2FCKFwHHTsCKrgBD%2BbTG3AWMeFo944Jn%2BmFqFdvOciRyxGQRVUW7g0Acz%2FHzWn6BWy%2F%2B6djN4NBkFzD41JARRQOO%2FpuQLN46FzSI0XaOkhF0z8BAoE%2Bq7NL24u0bHqt9xuBACPiaVsev%2FmXPFeQnskWPdh%2FHrbSyZ8Z77UAyRstjznHhIbBPKEBkMSds1HeMEbj6PCE9gPE65xjuVYAg%2F3WHDAbe9NnX82oANcAkR4fmj4xbVvKWj1M0bTpjqPqiIatcl6lu%2BV7DVoU9GYtr2Z12oITuW856ckMrsFpqw%2BUaKr1GHZk5AD9YrqXXbbulcfk5UraEr8alqPpmZVTwfd%2BF%2Ftdnf%2BXQEPQZ8xL1b98gsbegOIeWMbh32QcXpTFbxJQIbTGM8MxhdMZY64VN4ejsY0R%2BCLIvAuvzUeO%2BGDjWRoroTQo1S1RO3vAX91b%2F0JDLUpjorl%2B9%2B8j8lg3RbeEH0MobLAIa1y2lL1NPh3HC6CiqKoAxaK8TIiqP%2FOEtZzWbT4G1caqY2PUMTJr0sZEoI3mBZvkDMM3ZWYxEKi%2BiD%2F8hWlub0%2FN8yFaVwe5Z2AAgqhr%2BTsfohvBDiuQAMN2LIH2WInDRk8Hl8be5r2MMXNgdYGOqUBllJng7WLho9ImzRt8zi6bx3JguuoWRj6s8m0FmgrsF9em0HEmCsRlzFz5kG0c42POlMpld4aTUCZupjH7TGFvXAcLMec2FAvgs2Zh8TYlr8o1Tm1a8flcB9CSJ2Ze6Vt%2BVSFwRQMTkVC4%2BHxjC1WosLwjldK3fxhEETP%2FItay1L9rW46QAb4zhgdfZBlUaZ5D7kBsAkOGa9YHjqG%2B4d5nQoozzZW&X-Amz-Signature=7d35184e7351a80db8c3956d100fab47f9ad52055b152599a0bf6a99541a4878&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject#notion_record=block.0591f625-0dfc-4a98-bef8-120884faa004.e27ba36d-dc94-8119-9451-00031cc0d47c"></file>
Recorded catalog reused unchanged from v1; historical and partial, not a new scrape:
<file src="https://prod-files-secure.s3.us-west-2.amazonaws.com/e27ba36d-dc94-8119-9451-00031cc0d47c/aea42d1e-11f3-4a47-a1dd-f1f50eb1b525/BrainForge-recorded-catalog.json.gz?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Credential=ASIAZI2LB466TPWUNPGK%2F20261003%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20261003T045820Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjENv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLXdlc3QtMiJHMEUCIFq7IEHCyx%2FUUv2hxEHHof9aeEtVsBZOqAKucGlQspBzAiEAqTIhK5pbGpICDlNSxxsPWejKueTq5XeN1zWx0B8eRB0qiAQIo%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARAAGgw2Mzc0MjMxODM4MDUiDEA978lCx0Q2ixsrWircA6iiq1prm71jKk2eau6%2FCKFwHHTsCKrgBD%2BbTG3AWMeFo944Jn%2BmFqFdvOciRyxGQRVUW7g0Acz%2FHzWn6BWy%2F%2B6djN4NBkFzD41JARRQOO%2FpuQLN46FzSI0XaOkhF0z8BAoE%2Bq7NL24u0bHqt9xuBACPiaVsev%2FmXPFeQnskWPdh%2FHrbSyZ8Z77UAyRstjznHhIbBPKEBkMSds1HeMEbj6PCE9gPE65xjuVYAg%2F3WHDAbe9NnX82oANcAkR4fmj4xbVvKWj1M0bTpjqPqiIatcl6lu%2BV7DVoU9GYtr2Z12oITuW856ckMrsFpqw%2BUaKr1GHZk5AD9YrqXXbbulcfk5UraEr8alqPpmZVTwfd%2BF%2Ftdnf%2BXQEPQZ8xL1b98gsbegOIeWMbh32QcXpTFbxJQIbTGM8MxhdMZY64VN4ejsY0R%2BCLIvAuvzUeO%2BGDjWRoroTQo1S1RO3vAX91b%2F0JDLUpjorl%2B9%2B8j8lg3RbeEH0MobLAIa1y2lL1NPh3HC6CiqKoAxaK8TIiqP%2FOEtZzWbT4G1caqY2PUMTJr0sZEoI3mBZvkDMM3ZWYxEKi%2BiD%2F8hWlub0%2FN8yFaVwe5Z2AAgqhr%2BTsfohvBDiuQAMN2LIH2WInDRk8Hl8be5r2MMXNgdYGOqUBllJng7WLho9ImzRt8zi6bx3JguuoWRj6s8m0FmgrsF9em0HEmCsRlzFz5kG0c42POlMpld4aTUCZupjH7TGFvXAcLMec2FAvgs2Zh8TYlr8o1Tm1a8flcB9CSJ2Ze6Vt%2BVSFwRQMTkVC4%2BHxjC1WosLwjldK3fxhEETP%2FItay1L9rW46QAb4zhgdfZBlUaZ5D7kBsAkOGa9YHjqG%2B4d5nQoozzZW&X-Amz-Signature=0a7069dd0486b56c7ddba90690d481adc19ffa4031951fd180058fef05afb7d6&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject#notion_record=block.eaac65aa-e771-4107-b569-e682e766566e.e27ba36d-dc94-8119-9451-00031cc0d47c"></file>