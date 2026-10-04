#!/usr/bin/env python3
"""Evidence-Aware Warmstart Builder CLI.

Refactored to delegate directly to forge2_warmstart for create-only, fail-closed
warmstart generation and full provenance serialization.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from forge2_warmstart import build_evidence_aware_warmstart


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', default='backups/pre_v2_baseline/brain_memory.earnings4_run2.db')
    p.add_argument('--meta', default='migrated_runs/earnings4_run2/.epochs/c8336ac56f924355bf715f66b8e0157c/forge2_field_meta.json')
    p.add_argument('--out', required=True, help='Create-only destination path (must not exist)')
    p.add_argument('--size', type=int, default=20)
    p.add_argument('--explore-fraction', type=float, default=0.2)
    p.add_argument('--max-dataset-fraction', type=float, default=1.0)
    p.add_argument('--max-abs-correlation', type=float, default=0.8)
    p.add_argument('--min-residual-fraction', type=float, default=0.1)
    p.add_argument('--min-overlap', type=int, default=60)
    p.add_argument('--ridge', type=float, default=1e-6)
    args = p.parse_args()

    payload = build_evidence_aware_warmstart(
        args.db,
        args.meta,
        args.out,
        size=args.size,
        explore_fraction=args.explore_fraction,
        max_dataset_fraction=args.max_dataset_fraction,
        max_abs_correlation=args.max_abs_correlation,
        min_residual_fraction=args.min_residual_fraction,
        min_overlap=args.min_overlap,
        ridge=args.ridge,
    )
    print(f"Published create-only warmstart: {args.out}")
    print(f"  SHA-256: {payload['warmstart_file_hash']}")
    print(f"  Measured Core: {payload['warmstart_manifest']['measured_core_count']}")
    print(f"  Unverified Exploration: {payload['warmstart_manifest']['unverified_exploration_count']}")
    print(f"  Underfill Count: {payload['warmstart_manifest']['underfill_count']}")


if __name__ == '__main__':
    main()
