import asyncio
import json
import textwrap
from pathlib import Path
from urllib.parse import urlencode

import config
from network_engine import NetworkEngine

OPERATORS_PATH = Path(__file__).with_name("operators.json")


def _print_schema(label, rows):
    if not rows:
        print(f"  [{label}] no rows returned.")
        return
    sample = rows[0]
    print(f"  [{label}] {len(rows)} row(s); keys: {sorted(sample.keys())}")
    print(f"  [{label}] sample row:")
    print(textwrap.indent(json.dumps(sample, indent=2)[:1500], "    "))


async def probe_data_api(net):
    """Confirm the shape of the data-sets / data-fields endpoints WITHOUT
    harvesting everything. Prints the working parameter names, total counts,
    JSON keys, and one sample row from each, so we can lock the harvester
    schema (coverage / alphaCount / userCount / type / valueScore)."""
    base = {
        "instrumentType": config.DEFAULT_INSTRUMENT,
        "region": config.DEFAULT_REGION,
        "delay": config.DEFAULT_DELAY,
        "universe": config.UNIVERSES[0],
    }
    print("\n--- DATA API PROBE -------------------------------------------------")
    print(f"  filters: {base}")

    # 1) data-sets: this is where the per-category 'value score' lives.
    ds_params = urlencode({**base, "limit": 5, "offset": 0})
    ds_res = await net.request("GET", f"/data-sets?{ds_params}")
    ds_body = ds_res["json"] if isinstance(ds_res["json"], dict) else {}
    print(f"\n  GET /data-sets -> HTTP {ds_res['status_code']} (count={ds_body.get('count')})")
    _print_schema("data-sets", ds_body.get("results") or [])

    # 2) data-fields: one page (the API caps page size around 50).
    df_params = urlencode({**base, "limit": 50, "offset": 0})
    df_res = await net.request("GET", f"/data-fields?{df_params}")
    df_body = df_res["json"] if isinstance(df_res["json"], dict) else {}
    total = df_body.get("count")
    first_page = df_body.get("results") or []
    print(f"\n  GET /data-fields -> HTTP {df_res['status_code']} (count={total}, page_size={len(first_page)})")
    _print_schema("data-fields", first_page)

    # 3) confirm offset pagination advances (fetch the 2nd page if it exists).
    if total and total > 50:
        df2_params = urlencode({**base, "limit": 50, "offset": 50})
        df2_res = await net.request("GET", f"/data-fields?{df2_params}")
        df2_body = df2_res["json"] if isinstance(df2_res["json"], dict) else {}
        page2 = df2_body.get("results") or []
        first_id = first_page[0].get("id") if first_page else None
        page2_id = page2[0].get("id") if page2 else None
        advanced = bool(page2_id) and page2_id != first_id
        print(f"\n  offset pagination -> page2 size={len(page2)}, advanced={advanced} "
              f"(offset=0 id={first_id!r}, offset=50 id={page2_id!r})")

    # 4) confirm the dataset-scoped filter narrows results.
    ds_results = ds_body.get("results") or []
    if ds_results:
        sample_ds = ds_results[0].get("id")
        scoped = urlencode({**base, "dataset.id": sample_ds, "limit": 5, "offset": 0})
        sc_res = await net.request("GET", f"/data-fields?{scoped}")
        sc_body = sc_res["json"] if isinstance(sc_res["json"], dict) else {}
        print(f"\n  GET /data-fields?dataset.id={sample_ds} -> HTTP {sc_res['status_code']} "
              f"(count={sc_body.get('count')})")
    print("--- END PROBE ------------------------------------------------------\n")


async def main():
    """Verify connectivity and download operator metadata.

    config.py loads operators.json lazily, so importing config before this file
    has run is safe -- this script bootstraps that file. Run it once before the
    orchestrator (and re-run whenever WorldQuant updates its operator set).
    """
    net = NetworkEngine()
    try:
        res = await net.request("GET", "/operators")
        print(f"GET /operators -> HTTP {res['status_code']}")
        operators = res["json"]
        if res["status_code"] != 200 or not isinstance(operators, list) or not operators:
            print("Could not download operators. Check WQ_EMAIL/WQ_PASSWORD or WQ_COOKIE in .env.")
            return
        OPERATORS_PATH.write_text(json.dumps(operators, indent=2), encoding="utf-8")
        print(f"Wrote {len(operators)} operators to {OPERATORS_PATH.name}.")

        await probe_data_api(net)
    finally:
        await net.close()


if __name__ == "__main__":
    asyncio.run(main())
