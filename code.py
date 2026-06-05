"""Standalone smoke test: take a seed template, hot-swap {FIELD}, and simulate.

This is the SECURE replacement for the original scratch file. The old version
hard-coded a personal WorldQuant session token (a leaked secret) and duplicated
the auth / polling / simulation logic that now lives in network_engine.py and
config.py. This rewrite keeps the original behavior -- a quick batch test of one
template across several data fields -- but:
  * authenticates via .env (WQ_EMAIL/WQ_PASSWORD or WQ_COOKIE), never a token in code
  * reuses NetworkEngine (rate limiting, auth refresh, structured responses)
  * reuses config.build_simulation_payload so settings match the real pipeline
  * validates each mutated expression before spending a simulation

For a single ad-hoc expression use test_alpha.py; for the full search run
orchestrator.py. This file is just a fast manual sanity check.
"""

import asyncio
import random

import config
from network_engine import NetworkEngine
from syntax_validator import SyntaxValidator

# A seed template with a {FIELD} placeholder, mirroring the original intent.
# (Imagine the LLM produced this structure.)
SEED_TEMPLATE = "group_neutralize(rank(-1 * returns) * ts_rank({FIELD}, 10), SECTOR)"


async def _simulate_once(net, expression):
    payload = config.build_simulation_payload(expression, config.UNIVERSES[0], config.DECAYS[0])
    resp = await net.request("POST", "/simulations", json=payload)
    if resp["status_code"] not in (200, 201):
        print(f"   rejected: HTTP {resp['status_code']} -> {resp['json']}")
        return

    poll_url = resp.get("location")
    body = resp.get("json")
    if not poll_url and isinstance(body, dict):
        poll_url = body.get("location") or body.get("url")
    if not poll_url:
        print("   accepted but no poll URL returned.")
        return

    endpoint = poll_url.replace(config.WQ_BASE_URL, "")
    loop = asyncio.get_event_loop()
    deadline = loop.time() + config.SIMULATION_POLL_TIMEOUT_SECS
    while loop.time() < deadline:
        await asyncio.sleep(config.SIMULATION_POLL_INTERVAL_SECS)
        poll = await net.request("GET", endpoint)
        pbody = poll["json"] or {}
        status = str(pbody.get("status", "")).upper()
        if status in ("ERROR", "FAIL", "FAILED"):
            print(f"   error: {pbody.get('message') or pbody}")
            return
        if status == "COMPLETE" or pbody.get("alpha"):
            alpha_id = pbody.get("alpha")
            detail = await net.request("GET", f"/alphas/{alpha_id}")
            metrics = (detail["json"] or {}).get("is") or {}
            sharpe = metrics.get("sharpe", 0) or 0
            turnover = metrics.get("turnover", 0) or 0
            verdict = ("WINNER" if sharpe >= config.MIN_SHARPE and turnover <= config.MAX_TURNOVER
                       else "below threshold")
            print(f"   sharpe={sharpe:.3f} turnover={turnover * 100:.2f}%  -> {verdict}")
            return
    print("   timed out waiting for completion.")


async def execute_mutation_batch(template, max_tests=4):
    """Hot-swap {FIELD} with real data fields and simulate each variant.

    Inter-submission spacing / jitter is handled centrally by NetworkEngine's
    rate limiter, so this no longer needs its own sleep() calls.
    """
    print(f"Seed template: {template}")
    pool = config.DATA_DICTIONARY
    fields = random.sample(pool, min(max_tests, len(pool)))
    net = NetworkEngine()
    try:
        for i, field in enumerate(fields, start=1):
            mutated = template.replace("{FIELD}", field)
            print(f"\nTest {i}/{len(fields)}: {mutated}")
            ok, canonical = SyntaxValidator.parse_and_validate(mutated)
            if not ok:
                print("   invalid expression; skipping.")
                continue
            await _simulate_once(net, canonical)
    finally:
        await net.close()


if __name__ == "__main__":
    asyncio.run(execute_mutation_batch(SEED_TEMPLATE, max_tests=4))