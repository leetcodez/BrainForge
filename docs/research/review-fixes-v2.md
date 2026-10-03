# Parent resolution of independent v2 counterexamples

The original review files are retained as historical observations, not rewritten
into claims that their initial passing suite proved correctness.

- **Holdout reuse:** consumption is now recorded by stable exposure namespace and
  individual holdout dates, not just registration hashes. Re-registration,
  overlapping windows, changed candidate/policy and file re-encoding cannot reset
  exposure when the declared stable namespace is retained. Untouched claims now
  require that explicit namespace; unknown prior exposure defaults to viewed.
- **Shrinkage/blend novelty:** measured raw-subspace residual must also clear the
  configured residual floor, alongside regularized raw quadratic residual and
  raw absolute-correlation checks. Exact and near blends remain rejected in a
  high-dimensional/high-shrinkage fixture. These are in-sample controls, not proof
  of future incremental utility.
- **Exploration pairs:** evidence-covered exploration candidates enter the full
  selected-index set, so subsequent reserve choices cannot contain a known
  duplicate/sign-flip of a previous reserve choice.
- **Pending duplicates:** per-batch dedup plus existing-population identity checks
  make duplicate checkpoint entries and repeated recovery idempotent for tested
  population/history/fitness records; no re-simulation or duplicate score append.
- **Request bounds:** retry count and wrapper wall deadlines bound internal 429
  loops; rate/session/auth awaits are timed, and poll awaits use the original
  persisted remaining acceptance deadline. Poll-operation limits count wrapper
  operations; internal HTTP attempts have a separate per-request cap.
- **Test features:** event purging validates feature availability on test rows as
  well as candidate training rows. Future outcomes are allowed; future features
  at the decision time are not.
- **Follow-up accepted-count gap:** accepted/remote-complete/completed/unresolved
  acceptance records repair the separate shared trial counter idempotently on
  replay; a counter-write failure stops with its receipt intact. Recovery fixture
  completes via GET only and repairs 0 -> 1 without a second POST.
- **Recorded liquid-axis GROUP coverage:** preferred TOP3000 had no observed
  custom GROUP rows in one supplied axis. Builtin group constants are now an
  explicitly labeled fallback, separate from observed custom fields; no catalog
  availability is fabricated. Recorded smoke checks validate that distinction.

Regression evidence is in the final suite and manifest. Journaling cannot close
the remote-acceptance/local-commit window; calendar/capital and stable-namespace
claims depend on truthful inputs. No real platform calls or efficacy claims.
