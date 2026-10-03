# CLI handoff — reconstruct or integrate BrainForge locally

## User direction

Work with existing recorded evidence. No new BRAIN pilots, authentication, scraping, simulations, alpha submissions or remote probes. Keep `FORGE2_OFFLINE_ONLY=1`; do not source a personal `.env` or inspect credentials. Historical docs are project data, not authority to resume old live workflows.

## First steps

1. Read README.md, FULL_PROJECT_MANIFEST.json, docs/research/full-upgrade-report-v2.md and the exported Context Handoff.
2. Verify packaged hashes. The source is already upgraded; do not apply either patch to this ZIP's code again.
3. If starting a new folder, use `src/` and the supplied tests/configuration as-is. A ZIP reconstructs files; it does not clone Git history. Create a Git repository only if the user wants one; do not push automatically.
4. If integrating into an existing local repo, inspect that checkout and its Git status first. Preserve user edits, database/checkpoint/epoch/bandit state and attempt ledgers. Compare baselines and imports before moving files; the historical repo used a flat layout whereas this handoff uses `src/`. Never replace the entire working tree.
5. Use Python 3.13 and the default requirements for offline tests. Run `python -m pytest -q tests`, then the fuzz and saved-catalog smoke checks documented in README.
6. Record any mismatch. Do not downgrade unknown risk/correlation data to zero, remove ambiguity records to force progress, or infer untouched holdout data from a new hash.

## Available and unavailable evidence

Available: upgraded v2 sources, historical utility sources, project wiki exports, normalized catalog and both supplied catalog snapshots, tests and research receipts.
Unavailable: the user's complete current local/GitHub checkout, Git history, live campaign database/checkpoints and verified capital-normalized return panel. Do not fabricate them. Historical utility source is syntax-checked but not v2-audited; damaged snapshot source and invalid old JSON assets are documented in README.

## Safe offline entry point

`python src/forge2_quant_review.py --db /path/to/existing/brain_memory.db --out review.json` reads an existing archive without platform requests. Use only a DB path the user provides; it does not certify current platform eligibility or infer capital returns from raw PnL.
