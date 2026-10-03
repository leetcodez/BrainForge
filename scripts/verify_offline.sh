#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON" -m compileall -q src
"$PYTHON" -m pytest -q tests --junitxml=evidence/pytest.xml
"$PYTHON" evidence/fuzz_genetics.py
if [[ -n "${CATALOG:-}" ]]; then
  "$PYTHON" src/forge2_smoke_test.py --catalog "$CATALOG" --operators src/operators.json --outdir evidence/replay-smoke
else
  echo "Recorded-catalog smoke NOT run: set CATALOG to your normalized existing catalog."
fi
