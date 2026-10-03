"""Verify the immutable file inventory; no network required."""
import hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
m=json.loads((r/'FULL_PROJECT_MANIFEST.json').read_text())
errors=[]
for name,entry in m['files'].items():
    p=r/name
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
        errors.append(name)
if errors:raise SystemExit('Missing/changed: '+', '.join(errors))
print('Verified',len(m['files']),'packaged file hashes.')
