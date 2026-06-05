import asyncio
import json
from pathlib import Path

import config
from network_engine import NetworkEngine

OPERATORS_PATH = Path(__file__).with_name("operators.json")


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

        # Sanity-probe the data-fields endpoint for the default region (non-fatal).
        params = (
            f"?instrumentType={config.DEFAULT_INSTRUMENT}&region={config.DEFAULT_REGION}"
            f"&delay={config.DEFAULT_DELAY}&universe={config.UNIVERSES[0]}&limit=1"
        )
        fields_res = await net.request("GET", f"/data-fields{params}")
        body = fields_res["json"]
        count = body.get("count") if isinstance(body, dict) else None
        print(f"GET /data-fields -> HTTP {fields_res['status_code']} (count={count}).")
    finally:
        await net.close()


if __name__ == "__main__":
    asyncio.run(main())