"""Unpack supplied historical archives locally; never contacts BRAIN."""
from pathlib import Path
import tarfile
root=Path(__file__).resolve().parents[1]
out=root/'data'/'recorded-snapshots';out.mkdir(parents=True,exist_ok=True)
for name in ['recorded-snapshot.tgz','recorded-snapshot-narrow.tar.gz']:
    with tarfile.open(root/'evidence'/name) as archive:
        archive.extractall(out,filter='data')
print(out)
