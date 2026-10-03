"""Offline normalization of RECORDED snapshot listings. Never contacts BRAIN.
Usage: python forge2_build_catalog.py --input snapshot/raw/data-fields.json \
       --input snapshot_narrow/raw/data-fields.json --out brain_fields_merged.json
Later inputs win for duplicate field/settings records. Availability is observed
positive evidence only; missing tuples remain UNKNOWN, not proven invalid.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from forge2_storage import atomic_json


def build_catalog(inputs, output):
    import ijson  # streaming avoids loading ~1 GB of raw repeated rows
    fields = {}; axes=Counter(); occurrences=0; conflicts=0; sources=[]
    for path in map(Path,inputs):
        digest=hashlib.sha256()
        with path.open('rb') as fh:
            for block in iter(lambda:fh.read(1024*1024),b''):
                digest.update(block)
        sources.append({'file':path.name,'sha256':digest.hexdigest()})
        with path.open('rb') as fh:
            for row in ijson.items(fh,'slices.item.rows.item',use_float=True):
                fid=row.get('id')
                if not isinstance(fid,str) or not fid.isidentifier():
                    continue
                region=str(row.get('region') or '').upper()
                universe=str(row.get('universe') or '')
                try:delay=int(row['delay'])
                except (KeyError,ValueError,TypeError):continue
                if not region or not universe:continue
                occurrences+=1;axes[(region,delay,universe)]+=1
                if fid not in fields:
                    fields[fid]={k:row.get(k) for k in ['id','description','type','dataset','category','subcategory']}
                    fields[fid]['_availability']={}
                # Preserve the actual joint tuple and its own metrics.
                val=[float(row.get('coverage') or 0),float(row.get('pyramidMultiplier') or 1),
                     int(row.get('alphaCount') or 0),float(row.get('dateCoverage') or 0)]
                key=(region,delay,universe)
                previous=fields[fid]['_availability'].get(key)
                if previous is not None and previous != val:conflicts+=1
                fields[fid]['_availability'][key]=val
    if not fields:raise ValueError('No observed field/settings records in inputs')
    for fid,raw in fields.items():
        available=raw.pop('_availability')
        raw['availability']=[[*key,*value] for key,value in sorted(available.items())]
        raw['regions']=sorted({k[0] for k in available})
        raw['delays']=sorted({k[1] for k in available})
        raw['universes']=sorted({k[2] for k in available})
        raw['maxCoverage']=max(v[0] for v in available.values())
        raw['bestPyramidMultiplier']=max(v[1] for v in available.values())
        raw['maxAlphaCount']=max(v[2] for v in available.values())
        raw['dateCoverage']=max(v[3] for v in available.values())
    stats={'fields':len(fields),'listing_occurrences':occurrences,
           'regions_with_listing_rows':sorted({a[0] for a in axes}),
           'joint_axes':len(axes),'conflicting_records':conflicts,
           'complete':False,'sources':sources,
           'note':'Historical partial snapshots. Positive tuples only; no completeness claim.'}
    # Compact encoding keeps the normalized artifact significantly smaller.
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(output.suffix+'.tmp')
    with tmp.open('w') as fh:json.dump({'version':2,'fields':fields,'evidence':stats},fh,separators=(',',':'),allow_nan=False)
    tmp.replace(output)
    atomic_json(output.with_suffix('.evidence.json'),stats)
    return stats


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',action='append',required=True)
    ap.add_argument('--out',required=True)
    a=ap.parse_args();print(json.dumps(build_catalog(a.input,a.out),indent=2))

if __name__=='__main__':main()
