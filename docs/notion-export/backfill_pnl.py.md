```python
"""Backfill daily PnL for qualified alphas into the alpha_pnl table.

Runs entirely OFF TO THE SIDE of the orchestrator: it only READS alpha_ids from
alpha_population and WRITES the new alpha_pnl table, so it cannot affect the
running generator.

Usage:
    python backfill_pnl.py             # fetch PnL for all qualified candidates
    python backfill_pnl.py --dry-run   # show what WOULD be fetched, store nothing
    python backfill_pnl.py --all       # every alpha with a real id, not just qualified
"""
import argparse
import asyncio
import json

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine


def _parse_pnl_records(payload):
    """Defensively extract [(date, cumulative_pnl)] from a WQ pnl recordset.
    Handles {records: [[date, val], ...]} and {records: [{date:.., pnl:..}, ...]}."""
    if not isinstance(payload, dict):
        return []
    records = payload.get("records") or payload.get("results") or []
    out = []
    for row in records:
        date = val = None
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            date, val = row[0], row[-1]
        elif isinstance(row, dict):
            date = row.get("date") or row.get("Date")
            val = row.get("pnl", row.get("value", row.get("PnL")))
        if date is None or val is None:
            continue
        try:
            out.append((str(date), float(val)))
        except (TypeError, ValueError):
            continue
    return out


# WorldQuant generates recordsets (pnl, stats, ...) ASYNCHRONOUSLY: the first
# GET answers 200 with an EMPTY body + a Retry-After header while the recordset
# is still being built, and the rows only appear on a LATER GET. A single-shot
# fetch therefore reads the still-empty first response and reports "no PnL" for
# every alpha. These bound the re-GET poll.
PNL_POLL_MAX_ATTEMPTS = 8
PNL_POLL_INTERVAL_SECS = 2.0


async def _fetch_pnl(net, alpha_id, verbose=False):
    """Fetch one alpha's daily PnL, POLLING through WorldQuant's async recordset
    generation (200 + empty body + Retry-After until ready). Returns [] only
    after the poll budget is exhausted or the platform returns a terminal error
    (e.g. a 404 wrong-path), which `verbose` surfaces on the first alpha."""
    endpoint = config.WQ_PNL_ENDPOINT_TEMPLATE.format(alpha_id=alpha_id)
    target = endpoint
    for attempt in range(1, PNL_POLL_MAX_ATTEMPTS + 1):
        resp = await net.request("GET", target)
        status = resp["status_code"]
        if verbose and attempt == 1:
            body = resp.get("json")
            preview = json.dumps(body)[:300] if body is not None else "<no json>"
            print(f"  [diag] {alpha_id}: HTTP {status}, "
                  f"Retry-After={resp['headers'].get('Retry-After')}, "
                  f"location={resp.get('location')}, body={preview}")
        if status not in (200, 201):
            return []  # terminal (wrong path / gone) -- caller logs the skip
        series = _parse_pnl_records(resp.get("json") or {})
        if series:
            return series
        # 200 but empty => recordset still generating. Follow a Location if WQ
        # handed one back, else re-GET the same endpoint after the suggested
        # (or default) delay.
        if resp.get("location"):
            target = resp["location"]
        retry_after = resp["headers"].get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else PNL_POLL_INTERVAL_SECS
        except (TypeError, ValueError):
            delay = PNL_POLL_INTERVAL_SECS
        await asyncio.sleep(delay)
    return []


async def main(dry_run=False, include_all=False):
    db = DatabaseManager()
    db.init_db_sync()
    if include_all:
        rows = db.get_top_population_sync(limit=1000000)
        alpha_ids = sorted({r[10] for r in rows if r[10] and r[10] != "MANUAL_SEED"})
    else:
        candidates = db.get_submission_candidates_sync(
            config.MIN_SHARPE, config.MAX_TURNOVER, config.MAX_SELF_CORRELATION,
            min_turnover=getattr(config, "MIN_TURNOVER", 0.0),
        )
        alpha_ids = sorted({c[1] for c in candidates if c[1] and c[1] != "MANUAL_SEED"})

    already = set(db.alpha_ids_with_pnl_sync())
    todo = [a for a in alpha_ids if a not in already]
    print(f"{len(alpha_ids)} target alpha(s); {len(already)} already stored; {len(todo)} to fetch.")
    if dry_run:
        for a in todo:
            print(f"  would fetch PnL for {a}")
        db.close_sync()
        return

    net = NetworkEngine()
    stored = 0
    try:
        for idx, alpha_id in enumerate(todo):
            series = await _fetch_pnl(net, alpha_id, verbose=(idx == 0))
            if not series:
                print(f"  no PnL returned for {alpha_id} (skipped)")
                continue
            db.save_pnl_sync(alpha_id, series)
            stored += 1
            print(f"  stored {len(series)} PnL points for {alpha_id}")
    finally:
        await net.close()
        db.close_sync()
    print(f"Done. Stored PnL for {stored} alpha(s).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", dest="include_all")
    args = ap.parse_args()
    asyncio.run(main(dry_run=args.dry_run, include_all=args.include_all))
```