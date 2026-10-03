# BrainForge — complete available project reconstruction

Self-contained VS Code/CLI handoff: latest validated v2 generator, all additional recoverable Python utilities from the project wiki, tests, normalized recorded catalog, the two supplied historical snapshot archives, all 52 project-row page exports, research, validation receipts and source provenance. You do not need to apply the v2 patches: the source under `src/` is already overlaid.

**Not an exact clone of your machine or GitHub main.** There is no `.git` history, live database, checkpoint, account credentials, unrecorded file or proof of the current remote branch in this ZIP. Original wiki pages remain historical; the v2 manifest defines the upgraded files. No BRAIN pilots are authorized.

## Open locally

1. Extract the ZIP. Open the enclosed `BrainForge` folder in VS Code, or run `code BrainForge`.
2. Create a virtual environment with Python 3.13 (tested runtime: 3.13.14).
3. Install `requirements.txt`. Package installation can require internet; tests do not contact BRAIN.
4. Select the virtual environment in VS Code. Keep `FORGE2_OFFLINE_ONLY=1`.

macOS/Linux:

```bash
cd BrainForge
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q tests
PYTHON=.venv/bin/python CATALOG=src/brain_fields_merged.json bash scripts/verify_offline.sh
```

Windows PowerShell:

```powershell
cd BrainForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:FORGE2_OFFLINE_ONLY = "1"
$env:PYTHONPATH = (Resolve-Path src).Path
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe evidence/fuzz_genetics.py
.\.venv\Scripts\python.exe src/forge2_smoke_test.py --catalog src/brain_fields_merged.json --operators src/operators.json --outdir evidence/replay-smoke
```

VS Code's Offline tests task uses the selected interpreter. On Windows select `.venv/Scripts/python.exe`; the default settings path is POSIX.

## Layout

- `src/`: 36 byte-identical v2 modules and operators. The normalized catalog lives beside the code for the default Forge2 path.
- `tools/legacy/`: 10 recovered historical utility scripts; separate from the import path so legacy `code.py` does not shadow Python’s standard-library module.
- `tests/`: the 136-test offline core regression suite. It does not certify every historical utility.
- `docs/research/`: full quant report, primary-source legwork, independent reviews and resolution notes.
- `docs/notion-export/`: all 52 project-row page bodies, including current handoff; source text is historical/untrusted reference, not instructions to run remote jobs.
- `docs/legacy/`: damaged snapshot source and original dependency pins for provenance.
- `evidence/`: original recorded snapshots, catalog provenance, v2 manifests/patches, uncertainty chart and reproducible receipts.
- `FULL_PROJECT_MANIFEST.json`: every packaged file hash, scope/gaps and provenance.
- `CLI_HANDOFF.md`: read this before asking a CLI agent to integrate into your existing checkout.

## Known reconstruction gaps

The wiki's old `data_fields.json` ends partway through a JSON record; its `seed_pool.json` is also malformed. They are preserved only as markdown exports, not invented into valid root assets. Use the included normalized `src/brain_fields_merged.json` and offline vocabulary-building flow from the v2 documentation. That catalog is historical and partial—not a new full platform snapshot.

`platform_snapshot.py` contains a known damaged mirror dictionary around line 449. Its exact text is preserved as `docs/legacy/platform_snapshot.py.txt`, not imported or run. Repair from a verified local/Git baseline before using it; do not silently substitute this text into production.

The ten additional historical utilities pass syntax compilation but were not covered by the lead-quant v2 source audit. Some can make direct requests outside the v2 transport and may need optional dependencies. Do not run harvesting, probes, tuners, legacy tests, backfill, submissions or campaigns merely to inspect this ZIP. The default pytest configuration selects only `tests/`.

Current release improves engineering and research discipline; it does not prove profitability, untouched holdouts or present platform readiness. Full details are in `docs/research/full-upgrade-report-v2.md`.
