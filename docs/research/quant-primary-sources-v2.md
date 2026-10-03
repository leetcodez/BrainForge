# BrainForge v2: primary-source quant research and offline acceptance plan

Research only. No source changes, platform/BRAIN requests, pilots, profitability claims, or inferred number of independent strategies. Inspected `/data/brainforge-v2/src`; v1 is not the target implementation. The parent may be editing concurrently, so code observations describe inspected seams rather than an immutable commit. No current-v2 regression suite was run for this research task.

## Executive recommendation

Implement the data/interval contract and durable-attempt safety before interpreting stronger statistics. Add serial-aware **conditional, fixed-strategy** uncertainty; train-only shrinkage and forward marginal utility; and semantics-preserving identity. Keep family-selection corrections, predictive portfolio utility, and remote-execution durability separate. None is evidence of profitability or an excuse to run another live pilot.

Current positive seams: `forge2_statistics.daily_changes` matches both interval endpoints; diversification already uses common complete observations rather than a pairwise-stitched matrix; `forge2_policy` fingerprints runtime/settings/catalog information; the trial ledger records full payload variants. Preserve these. Existing `calculate_dsr`, `estimate_pbo`, scalar correlation penalties, canonicalization, and accepted-POST handling do not yet supply the guarantees below.

## 1. Establish a PnL/return contract before applying return inference

**Inspected seam.** `forge2_statistics.py:9` differences dated values and allows gaps up to four calendar days. Those outputs are **interval PnL increments** if input values really are cumulative cash PnL. A Friday-to-Monday trading interval may be valid; a missing trading-day observation producing a two-session change is not automatically a daily observation. Orchestrator PnL parsing accepts positional last-column values or `pnl`/`value` fields without a sufficiently explicit units/schema/capital contract. The newer `trackRecordLength` use is better than position `longCount`, but a fallback observation count cannot certify inference.

**Implementable rule.** Persist source field names, currency, cumulative/incremental status, net/gross costs, calendar, start/end timestamps, missingness, capital basis, source/data hash, and observed increment count. For cumulative cash PnL C:

```
x_t = C_t - C_(t-1)
r_t = x_t / B_(t-1)       only when positive, ex-ante capital B is known
```

Do not divide by cumulative PnL: it is not an account-wealth denominator. If total account wealth and external flows are known, specify a separate flow-timing-consistent return convention. Do not synthesize either denominator from an undocumented platform metric.

Without a capital basis, report a **PnL increment mean/volatility ratio**, not a verified investment-return Sharpe. A fixed positive scaling leaves this ratio and Pearson correlation unchanged; time-varying capital does not. Cash PnL and a dimensionless risk-free return cannot be directly subtracted. Lo's inference is framed for return processes; its time-aggregation results require an explicit process and sampling convention.[^https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios]

**Offline acceptance.** Fixtures distinguish cash increments, normalized returns, cumulative wealth, duplicate timestamps, missing sessions, weekends, and changing capital. Same endpoint pairs align; different endpoint pairs never align merely by end date. Reject inference requiring a regular calendar when interval duration is unknown. Never zero-fill or forward-fill missing performance returns. Missing T is `unavailable`, not an invented confidence interval.

## 2. Add a HAC delta-method standard error for a fixed strategy's Sharpe

**Inspected seam.** `oos_deflation.py:59` uses IID skew/kurtosis variance and a trials correction, without a raw return-panel argument. That is not dependence-aware Sharpe inference. It also returns annualized Sharpe multiplied by a probability, rather than returning just a DSR probability; retain distinct field names for probability and heuristic fitness.

For T regularly sampled, finite, dimensionless excess returns, define population-convention estimates:

```
mu = mean(r)
sigma² = mean((r-mu)²)
S = mu/sigma
psi_t = (r_t-mu)/sigma
        - mu/(2 sigma³) * ((r_t-mu)² - sigma²)
gamma_k = (1/T) sum[t=k+1..T] (psi_t-mean(psi))(psi_(t-k)-mean(psi))
Omega = gamma_0 + 2 sum[k=1..L] (1-k/(L+1))*gamma_k
SE(S) = sqrt(Omega/T)
CI = S +/- z_(1-alpha/2)*SE(S)
```

This is the delta-method influence function of mean divided by standard deviation with Bartlett/Newey–West long-run variance. Equivalently use moment vector `(mean(r),mean(r²))`, variance `v=m2-m1²`, and gradient `(m2/v^(3/2), -m1/(2v^(3/2)))`. Newey–West establishes a positive-semidefinite HAC construction; Ledoit–Wolf directly discusses HAC and time-series-bootstrap inference for Sharpe differences.[^https://www.nber.org/papers/t0055][^http://www.ledoit.net/jef_2008pdf.pdf]

**Important pitfall.** HAC of returns alone estimates mean uncertainty, not Sharpe uncertainty. The influence series includes variance/squared-return fluctuations. For paired strategies use `psi_A-psi_B` on the same intervals to infer `S_A-S_B`; adding separate standard errors ignores their covariance. Finite moments, weak dependence, and sufficiently stable stationarity remain assumptions. HAC is not a regime-change cure.

Under IID data the influence variance reduces to `1 - skew*S + (full_kurtosis-1)*S²/4`; normal IID gives `1+S²/2`. These are useful sanity checks, not a reason to assume IID. Match variance/skew/kurtosis conventions exactly. Select bandwidth using development data or a declared rule, require L<T and sufficient observations, and report bandwidth. Refuse zero volatility and materially negative/nonfinite long-run variance; only tolerate and flag numerical roundoff. No universal short-history accuracy guarantee.

**Offline acceptance.** Analytic influence-gradient check; L=0 normal/IID limit; paired identical strategies yield zero difference with a defined degenerate status; reproducible AR and volatility-clustered synthetic series; independent hand-calculated Bartlett fixture. Dependence tests should check coverage across many deterministic simulation seeds with tolerance, not assert every autocorrelated sample has a larger SE. No substitution of an “effective T” into DSR, and no claim this CI corrects adaptive strategy selection.

## 3. Separate horizon Sharpe, conventional annualization, and long-run uncertainty

For a stationary **additive** q-period return sum and lag covariances gamma:

```
Var(sum[t=1..q] r_t) = q*gamma_0 + 2*sum[k=1..q-1] (q-k)*gamma_k
S_q = sqrt(q)*S_1 / sqrt(1 + 2*sum[k=1..q-1] (1-k/q)*rho_k)
```

This directly follows from covariance expansion; it is not an exact formula for compounded simple returns. Lo specifically warns that square-root-of-time Sharpe conversion is valid only under special circumstances.[^https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios]

**Implementable interface.** Keep separately named outputs: per-observation ratio, conventional `sqrt(q)*S` display, estimated additive-horizon ratio where lag estimates support it, and HAC SE of the chosen estimator. A long-run signal ratio `sqrt(q)*mu/sqrt(long_run_variance(r))` is another approximation, not the exact finite-q horizon statistic or the SE of Sharpe. Multiplying a per-period CI by sqrt(q) only produces a CI for that conventional scaled statistic.

**Offline acceptance.** IID covariance recovers sqrt(q); positive and negative autocovariance fixtures recover the direct covariance of the additive sum; changing sampling interval refuses a daily-to-year conversion. Never silently set unobserved high-order lags to zero and present a precise annual horizon result.

## 4. Use synchronized studentized block bootstrap for paired uncertainty

Künsch's primary work develops resampling for dependent stationary observations. Politis–Romano explicitly describes fixed-length moving blocks and a stationary bootstrap with geometric random block lengths, including circular wraparound.[^https://projecteuclid.org/journals/annals-of-statistics/volume-17/issue-3/The-Jackknife-and-the-Bootstrap-for-General-Stationary-Observations/10.1214/aos/1176347265.short][^https://www.ssc.wisc.edu/~bhansen/718/Politis%20Romano.pdf]

**Implementable default.** For a contiguous complete T-by-p increment/return panel, enumerate overlapping length-l blocks starting at 1 through T-l+1; sample ceil(T/l) blocks with replacement, concatenate, and truncate to T. Every strategy column uses **the identical sampled row-index vector**. Do not resample cumulative levels, each column independently, or artificial missing-data concatenations. Do not accidentally wrap the last block to the first unless explicitly choosing the stationary/circular scheme. For the stationary version, restart at a uniformly selected row with probability p; mean block length is 1/p.

For a fixed Sharpe difference Delta, use bootstrap-t:

```
t_b* = (Delta_b* - Delta_hat) / SE_b*
CI = [Delta_hat - quantile_(1-alpha/2)(t*)*SE_hat,
      Delta_hat - quantile_(alpha/2)(t*)*SE_hat]
```

Ledoit–Wolf recommends studentized time-series-bootstrap confidence intervals for Sharpe differences and distinguishes confidence-interval resampling from generating data under a testing null.[^http://www.ledoit.net/jef_2008pdf.pdf] Do not label `fraction(S_b*>0)` a calibrated p-value. Report failed/degenerate replicates and refuse an interval when too few remain; a hand-picked successful subset is invalid.

**Caveats.** Stationarity/weak-dependence/moment assumptions remain; studentization can be unstable with short samples. Development-only block-length sensitivity is mandatory. The asymptotic regime has l growing but l/T shrinking; a fixed magic cube-root rule is not universally valid. If adopting the Politis–White automatic selector, account for the published Patton–Politis–White correction, not only the 2004 formula.[^https://public.econ.duke.edu/~ap172/Politis_White_2004.pdf][^https://www.tandfonline.com/doi/abs/10.1080/07474930802459016]

**Offline acceptance.** Seed plus panel hash reproduces sampled indices, intervals, and CI. Resampled clones stay clones; paired opposites retain their dependence. Block length 1 matches the corresponding IID resampling algorithm. Test uneven T truncation, forbidden gap-crossing blocks, constant columns, and bootstrap SE failures. Validate coverage on offline dependent-process ensembles. Number of blocks/replicates is not an independent-strategy count.

## 5. Make forward validation event-aware; a sample gap is not automatic purging

`TimeSeriesSplit` uses chronological prefix training; `gap` excludes a number of training-tail samples, and comparable fold durations assume equally spaced observations. It does not know label/holding intervals or causal availability.[^https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html] López de Prado's primary description identifies purging/embargo as protection against overlapping-label and serial-conditionality leakage.[^https://www.quantresearch.org/Innovations.htm]

**Proposed engineering predicate.** Store the outcome-information interval `[s_i,e_i]` for every training event. For validation outcome union V, purge training events whose intervals intersect V. For a single closed validation span `[v0,v1]`, overlap is `s_i<=v1 and e_i>=v0`; document boundary conventions. Train only on decisions preceding validation and labels that were actually available at the training cutoff. Use the union of actual validation outcome intervals when outcomes extend beyond the last validation decision date. Separately require each feature's `available_at <= decision_time`.

An AST's maximum trailing feature lookback determines warmup, not necessarily target/holding purge length. Causal trailing warmup can read earlier history without fitting on validation outcomes. In strict forward folds no future observations enter that fold's training, so a post-test embargo removes nothing there; apply appropriate embargo when a non-forward scheme permits later training rows, and enforce outcome availability when rolling to the next forward fold.

**Critical limitation.** A globally generated candidate pool using the complete archived history is already selected with future information. Splitting only its final score series cannot retroactively make discovery out-of-sample. Label it conditional evaluation of a fixed selected pool, or run the entire candidate-generation/selection pipeline fold-locally using already recorded offline data where that is possible—never propose new BRAIN pilots to fix this.

**Offline acceptance.** Variable holding horizons, inclusive boundary events, delayed observations, rolling features, irregular calendars, and deliberately leaking examples. Assert no overlap, no future availability, and train-only fitting of normalizers, covariance, surrogate, weights, thresholds, and mutation allocation. Hash fold membership before scoring.

## 6. Seal the final holdout and correctly name the current PBO diagnostic

**Inspected seam.** `oos_deflation.py:229` derives an OOS rank from a single collection of IS/OOS pairs. Its own simplified treatment is not a full combinatorially symmetric cross-validation PBO estimate.

Bailey et al. define CSCV over a synchronized performance matrix of candidate columns and time rows: split rows into an even number of blocks, enumerate symmetric half-block IS/OOS assignments, select the best IS column, compute its relative OOS rank omega, transform `lambda=log(omega/(1-omega))`, and estimate PBO as the fraction of negative logits. Specify rank orientation and endpoint convention. This is a fixed-pool selection diagnostic, not a guarantee of chronological deployability or of all adaptive trials ever attempted.[^https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf]

**Implementable rules.** Rename the current output to a single-split winner OOS-rank diagnostic, or implement and label actual CSCV with resource limits. Maintain a final chronological holdout artifact inaccessible to bandit, scouts, mutation search, covariance/weight fitting, and threshold tuning. Persist a one-use evaluation receipt with data, candidate, policy and protocol hashes. If results trigger refinement, that holdout has become development data; record this rather than repeatedly calling it final. A sealed holdout reduces leakage but does not eliminate all selection bias, particularly if its data was already available to earlier discovery.

Do not estimate an independent N from correlations, covariance rank, block counts, or trial payload count. Keep observed hypothesis/settings counts as an inventory, and label any multiplicity-adjusted statistic by its explicit assumptions. A serial-aware conditional CI does not by itself validate the IID DSR formula after adaptive discovery.

**Offline acceptance.** Separate storage/API access tests; deliberate holdout read from a selector fails. Deterministic small CSCV matrix checked by enumeration; ties and logit endpoints handled consistently. Re-evaluation records reused/consumed status, never a fresh holdout. No source-data completeness => no PBO estimate.

## 7. Add train-only covariance shrinkage, but do not confuse regularization with diversity

**Inspected seam.** Common-observation correlation/eigen diagnostics in `forge2_statistics.py:20` are a sensible PSD starting point; max-pairwise penalties in `oos_deflation` and selection modules are not a portfolio covariance estimator.

For centered complete training panel X with p columns:

```
S = X'X/T
m = trace(S)/p
Sigma_hat = (1-delta)*S + delta*m*I
```

This is the Ledoit–Wolf identity-target estimator exposed by scikit-learn; delta is estimated, not chosen because it produces attractive ranks. Original Ledoit–Wolf results concern a well-conditioned covariance estimator and an asymptotic risk criterion, not arbitrary missingness or serial-aware inference.[^http://ledoit.net/Well-conditioned2004.pdf][^https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html]

**Implementation choices.** Fit means/scales and shrinkage on training only; record centering, ddof convention, target, delta, eigenminimum, condition, panel members, common interval count and hash. Identity-target shrinkage is scale-sensitive: require commensurable economic units or use training-standardized data and explicitly transform back with the training scale matrix. Constant-correlation shrinkage is a different estimator; do not describe sklearn's identity-target implementation as that method. Its `block_size` controls memory, not temporal resampling.

Do not pairwise-delete each covariance entry independently: that can create a non-PSD matrix. Default to a predeclared common-observation cohort; if too few complete intervals, return `insufficient`, shrink the cohort by a declared rule, or use a separately specified missing-data estimator. Neither zero-fill nor “just shrink the pairwise matrix” repairs arbitrary observation bias. IID shrinkage theory is not a HAC guarantee for serial data; distinguish a numerically regularized one-period risk matrix from long-run covariance used for mean inference.

**Offline acceptance.** Clone/near-clone and p>T panels remain finite and PSD; manual matrix matches sklearn convention; holdout changes do not change fitted covariance; unequal units are rejected or transformed explicitly. Synthetic missingness yields declared coverage failures. Shrinkage lifts clone eigenvalues and can increase entropy rank mechanically: never call that extra independent economic dimensions.

## 8. Select candidates by marginal basket usefulness, not max absolute correlation alone

For centered training returns of an existing basket's component panel X and candidate c, fit ridge replication coefficients:

```
b = solve(Sigma_XX + lambda*I, Sigma_Xc)
e_t = c_t - b'X_t
Var(e) = sigma_c² - 2*b'Sigma_Xc + b'Sigma_XX*b
```

The unregularized inverse special case reduces to the familiar Schur complement. **Do not use that simplified residual-variance formula for ridge b.** Apply frozen training means and coefficients to validation rows. This is a proposed engineering use of covariance, not a claim that a paper validates this exact BrainForge selector. Shrinkage supports numerical conditioning, but identity injection can manufacture positive residual variance even for observed clones; keep raw clone checks and held-forward replication error separate.[^http://ledoit.net/Well-conditioned2004.pdf]

For baseline basket return p and added weight a in c, a fixed-weight mean–variance utility difference is:

```
Delta J(a) = a*mu_c - gamma*a*Cov(p,c)
             - (gamma/2)*a²*Var(c) - incremental_cost(a)
```

This is algebra from `J=mean(portfolio)-gamma*Var(portfolio)/2-cost`, not a profitability forecast. Choose weights, constraints, risk preference and cost assumptions on training; evaluate the same frozen construction forward, or nest all reoptimization inside each training fold. Unit/capital contracts from #1 apply. Missing correlation is unknown, not evidence of independence. Strong negative correlation can be a useful hedge, so an absolute-correlation novelty penalty must not be presented as marginal utility. Eligibility/quality gates stay hard even if a weak candidate diversifies.

**Offline acceptance.** Identical candidate adds zero replication novelty before shrinkage; a linear combination of several elites is detected even when each pairwise correlation is modest. Negative-correlation hedge example differs from an alpha novelty example. Ridge residual formula agrees with directly computed centered residual variance. Train-fitted weights remain unchanged when validation outcomes change. Correlation absence gets a coverage status, never a fabricated zero.

## 9. Replace algebraic canonicalization with semantics-preserving executable identity

**High-risk inspected seam.** `syntax_validator.py:93` flattens and sorts addition/multiplication trees; its commutative-call list sorts all positional arguments. These transformations can change executed floating-point results and may move optional positional control roles. For instance, `(1e16 + -1e16) + 1` and `1e16 + (-1e16 + 1)` give different standard floating-point results, yet reassociation can merge them.

LLVM explicitly classifies floating-point reassociation as otherwise unsafe and permits it only under stated fast-math assumptions; NaN/infinity/signed-zero assumptions are distinct permissions.[^https://llvm.org/docs/LangRef.html#fast-math-flags] GP operators can also implement protected rather than ordinary algebra: gplearn's protected division returns a defined value near zero, with other protected domain operations. This illustrates why a real-number identity is not a DSL equivalence; it is **not evidence of BRAIN's exact operator behavior**.[^https://gplearn.readthedocs.io/en/latest/intro.html]

**Implementable keys.** Keep (a) raw expression for provenance, (b) executable AST identity preserving tree, positional order, exact literal/value/type distinctions and operator identity, (c) an optional coarse motif/similarity key that never merges paid evaluations or score evidence. Normalize insignificant whitespace and parser-equivalent parentheses; reject unsupported constructs. Bind named roles with the partial checker, but do not claim a complete type/semantic proof. Only reorder inputs/keywords or simplify where the actual catalog's evaluation/missingness/control semantics justify it. Retain signed zero and do not silently equate integers/floats where execution can distinguish them.

No `x/x -> 1` at zero/missing values; no distributivity across clipping/winsorizing/ranking/time-series operators; no constant folding requiring undocumented NaN filtering. Clipping already violates linear distribution. Sampling a few rows can falsify equivalence but cannot prove an identity. Include full executed settings, execution/catalog version and data version in evaluation identity; keep derived scoring-policy versions separately so scores can be recomputed without conflating distinct evaluations.

**Offline acceptance.** Preserve the adversarial rounding example, zero/NaN/infinity/signed-zero cases, nested tree order and named/control arguments. Whitespace-only forms share a key. Coarse motif collisions remain distinct execution/evidence records. Existing historical canonical keys need a versioned migration—not retrospective rewriting of executable evidence.

## 10. Budget hypotheses, dispatch attempts, and uncertain acceptances separately

**Inspected seam.** `forge2_trials.py` records observed payload variants; those are valuable attempted-hypothesis inventory but not complete dispatch/acceptance accounting. The orchestrator records after observing HTTP acceptance, leaving attempts with lost responses outside that evidence. Transport retries in `network_engine.request` can consume further remote work.

**Implementable rule.** Atomically reserve an attempt and capacity before every possible POST; enforce budgets at a shared adapter covering seeding, refinement, parameter grids, negation and retries. Maintain separate counts for proposals, executable identities, expression/settings/data hypotheses, dispatch attempts, known acceptances, ambiguous acceptances, completed results and cached reuses. Unknown acceptance retains a conservative capacity reservation until a documented resolution; do not refund it merely because local polling expired. Local reservations/counters and state transitions should be one SQLite transaction.[^https://sqlite.org/lang_transaction.html]

Payload variants and retries are not independent statistical trials. Cache hits need no new dispatch budget. Identical hypotheses may still have multiple costly attempts. Bound simultaneous unresolved jobs, total dispatch count, poll requests and elapsed time separately; record why a budget closes a run. Research/offline mode must hard-disable remote submission, not merely suppress a favored caller.

**Offline acceptance.** Concurrent reserve-at-limit permits at most the configured number. Every source path hits the same mocked adapter. Cache reuse consumes zero dispatches; timeout keeps an ambiguous reservation; replay never creates a new reservation. Retry accounting distinguishes a changed payload from a repeated dispatch of the same hypothesis. No live calls in tests.

## 11. Journal accepted handles durably; explicitly refuse an exactly-once claim

**High-risk inspected seam.** `orchestrator` records the trial after observed acceptance (around line 1054); accepted polling handles/deadlines are not a full durable attempt state machine. `network_engine.py:445` retries transport failures/5xx without an adequate method-specific non-idempotency distinction. A POST may have been accepted remotely before its response or local commit was lost.

RFC 9110 says clients should not automatically retry non-idempotent requests unless they know the semantics are idempotent or can establish the original was never applied. A provider-verified deduplication contract would change the design; it must not be invented for this platform.[^https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2]

**Minimal durable states.** `RESERVED -> DISPATCHING -> ACCEPTED(handle) -> TERMINAL` with explicit `AMBIGUOUS`, `EXPIRED_UNRESOLVED`, and locally aborted-before-dispatch states. Persist full payload/identity/settings hash, attempt ID, creation/dispatch time, observed accepted handle, absolute polling deadline, response metadata and result/enrichment receipt. Commit the accepted handle immediately when observed, before further awaits. On restart, recover known handles with bounded read-only polls, never resubmit them. An acceptance lacking a usable handle is quarantined, not silently treated as a new candidate. Unknown dispatch completion becomes ambiguous; any reconciliation must use an already authorized/documented provider mechanism, not new exploratory calls.

**Unavoidable limit.** A durable pre-send intent cannot close the crash window between remote acceptance and local receipt commit. Without server idempotency/reconciliation, it is impossible to promise exactly-once remote submission. Promise durable local accounting, conservative no-automatic-resubmission of ambiguous jobs, and idempotent local terminal ingestion instead. POST retries after a timeout or 5xx are unsafe absent the verified contract; GET polling can be independently retried under a bound. An expired local deadline neither cancels nor proves completion of a remote job. Preserve absolute deadlines across restarts; never reset them indefinitely.

**Offline acceptance.** Fault injection before send, after mock remote acceptance before local commit, after accepted-handle commit, after terminal receipt before scoring, and repeated terminal replay. Known accepted handle resumes only GET; ambiguous state never POSTs; repeated terminal ingestion neither double-learns nor double-counts; missing handle and stale policy produce visible quarantine; expired absolute deadlines stop polling and retain unresolved status. Tests must use a fake transport and local database only.

## Suggested implementation order and honest output labels

1. **Safety/provenance:** #1, #9–11. Prevent semantics changes, silent unit substitution, unsafe retry and budget loss.
2. **Evaluation discipline:** #5–6. Otherwise more sophisticated statistics still evaluate a leaked selection procedure.
3. **Conditional inference:** #2–4. Store assumptions, sample calendar, T, bandwidth/block length and validation coverage alongside each interval.
4. **Portfolio usefulness:** #7–8, conditional on usable aligned data and explicit cost/capital assumptions.

Prefer outputs such as `pnl_increment_ratio`, `conditional_hac_ci`, `paired_block_bootstrap_ci`, `single_split_oos_winner_rank`, `cscv_pbo_fixed_pool`, `regularized_training_covariance`, `forward_marginal_utility`, and `unresolved_remote_attempt`. Do not call them independent N, probability of future profit, validated live alpha, exactly-once platform execution, or full semantic type safety.

## Primary/official source register and access caveats

- Lo (2002), *The Statistics of Sharpe Ratios*: CFA publisher abstract verified; primary article DOI `10.2469/faj.v58.n4.2453`. Full author PDF was not accessible in this pass. The additive-horizon formula above is explicitly a covariance expansion, not an unverifiable quotation of an equation number. https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios
- Newey–West (1987), primary NBER working-paper abstract and original scanned paper retrieved. HAC formula also cross-checked against the directly relevant Sharpe-inference paper. https://www.nber.org/papers/t0055
- Ledoit–Wolf (2008), *Robust performance hypothesis testing with the Sharpe ratio*, author-hosted original article; extracted relevant HAC/studentized-bootstrap discussion. http://www.ledoit.net/jef_2008pdf.pdf
- Künsch (1989), original publisher record; Politis–Romano (1994), original scanned article mirrored by a university, with comprehensive extraction of block construction and limitations. https://projecteuclid.org/journals/annals-of-statistics/volume-17/issue-3/The-Jackknife-and-the-Bootstrap-for-General-Stationary-Observations/10.1214/aos/1176347265.short ; https://www.ssc.wisc.edu/~bhansen/718/Politis%20Romano.pdf
- Politis–White (2004), original paper, and Patton–Politis–White (2009), correction publisher record; automatic-selector implementation details need the corrected equations before coding. https://public.econ.duke.edu/~ap172/Politis_White_2004.pdf ; https://www.tandfonline.com/doi/abs/10.1080/07474930802459016
- Ledoit–Wolf (2004), author-hosted original covariance article; official sklearn API documents the precise identity target. http://ledoit.net/Well-conditioned2004.pdf ; https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html
- Official sklearn `TimeSeriesSplit`; López de Prado's author description; Bailey et al.'s author-hosted original PBO paper. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html ; https://www.quantresearch.org/Innovations.htm ; https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Official LLVM fast-math rules and gplearn protected-operator documentation. These justify caution about algebra, not any undocumented BRAIN execution semantics. https://llvm.org/docs/LangRef.html#fast-math-flags ; https://gplearn.readthedocs.io/en/latest/intro.html
- RFC 9110 section 9.2.2 and official SQLite transaction semantics. Neither establishes platform-specific idempotency support. https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2 ; https://sqlite.org/lang_transaction.html
