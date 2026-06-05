import asyncio

import config
from db_manager import DatabaseManager
from network_engine import NetworkEngine


async def submit():
    """Submit the best qualifying alphas to WorldQuant.

    Candidates are gated at the SQL level on the same criteria the orchestrator
    used to promote them: realized IS Sharpe >= MIN_SHARPE, turnover <=
    MAX_TURNOVER, and stored realized self-correlation <= MAX_SELF_CORRELATION.
    Ordered by fitness (deflated) so the most robust alphas go first, capped at
    MAX_SUBMISSIONS_PER_RUN.
    """
    db = DatabaseManager()
    db.init_db_sync()
    candidates = db.get_submission_candidates_sync(
        config.MIN_SHARPE, config.MAX_TURNOVER, config.MAX_SELF_CORRELATION
    )
    if not candidates:
        print("No submission candidates meet the gate.")
        db.close_sync()
        return

    net = NetworkEngine()
    submitted = 0
    try:
        for expr, alpha_id, sharpe, turnover, fitness, max_corr in candidates:
            if submitted >= config.MAX_SUBMISSIONS_PER_RUN:
                print(f"Reached submission cap ({config.MAX_SUBMISSIONS_PER_RUN}).")
                break
            if not alpha_id or alpha_id == "MANUAL_SEED":
                continue
            res = await net.request("POST", f"/alphas/{alpha_id}/submit")
            if res["status_code"] in (200, 201):
                submitted += 1
                corr_txt = f"{max_corr:.3f}" if max_corr is not None else "n/a"
                print(f"Submitted {alpha_id} | sharpe={sharpe:.3f} turnover={turnover:.3f} "
                      f"fitness={fitness:.4f} self_corr={corr_txt}")
            else:
                print(f"Submit failed for {alpha_id}: HTTP {res['status_code']} -> {res['json']}")
    finally:
        await net.close()
        db.close_sync()
    print(f"Done. Submitted {submitted} alpha(s).")


if __name__ == "__main__":
    asyncio.run(submit())
    