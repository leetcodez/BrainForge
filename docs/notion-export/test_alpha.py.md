```python
import asyncio
import sys

import config
from llm_seed_generator import LLMSeedGenerator
from network_engine import NetworkEngine
from syntax_validator import SyntaxValidator


async def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else LLMSeedGenerator.fill_template(config.QUANT_TEMPLATES[0])
    ok, expression = SyntaxValidator.parse_and_validate(raw)
    if not ok:
        print(f"Invalid expression: {raw}")
        return
    print(f"Testing: {expression}")

    net = NetworkEngine()
    try:
        payload = config.build_simulation_payload(expression, config.UNIVERSES[0], config.DECAYS[0])
        res = await net.request("POST", "/simulations", json=payload)
        print(f"POST /simulations -> HTTP {res['status_code']}")
        if res["status_code"] not in (200, 201):
            print(res["json"])
            return

        poll_url = res.get("location")
        if not poll_url and isinstance(res["json"], dict):
            poll_url = res["json"].get("location") or res["json"].get("url")
        if not poll_url:
            print("No poll URL returned.")
            return

        endpoint = poll_url.replace(config.WQ_BASE_URL, "")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + config.SIMULATION_POLL_TIMEOUT_SECS
        alpha_id = None
        while loop.time() < deadline:
            await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
            poll = await net.request("GET", endpoint)
            pbody = poll["json"] or {}
            status = str(pbody.get("status", "")).upper()
            if status in ("ERROR", "FAIL", "FAILED"):
                print(f"Simulation failed: {pbody}")
                return
            if status == "COMPLETE" or pbody.get("alpha"):
                alpha_id = pbody.get("alpha")
                break
        if not alpha_id:
            print("Timed out waiting for the simulation to complete.")
            return

        detail = await net.request("GET", f"/alphas/{alpha_id}")
        metrics = (detail["json"] or {}).get("is") or {}
        print(f"alpha_id = {alpha_id}")
        print(f"  sharpe   = {metrics.get('sharpe')}")
        print(f"  turnover = {metrics.get('turnover')}")
        print(f"  fitness  = {metrics.get('fitness')}")
        print(f"  returns  = {metrics.get('returns')}")
    finally:
        await net.close()


if __name__ == "__main__":
    asyncio.run(main())
```