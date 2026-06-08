import json
from pathlib import Path

import config
from db_manager import DatabaseManager
from syntax_validator import SyntaxValidator

# Diversified seed expressions drawn from documented, robust signal families:
#   * cross-sectional & time-series reversal / momentum (Kakushadze, "101
#     Formulaic Alphas", arXiv:1601.00991)
#   * the classic factor zoo -- low-volatility, risk-adjusted momentum, quality/
#     value (earnings yield)
# These are signal STRUCTURES, not pre-scored alphas: they are stored UNSCORED
# (sharpe = NULL) so the orchestrator MUST actually simulate them before
# trusting them -- we never fabricate metrics for a seed, and the OOS-deflation
# / self-correlation safeguards still gate everything downstream. Requires
# operators.json to exist (run probe_wq.py first) so the validator can check
# operator names/arity. Neutralizations are spread across SECTOR/INDUSTRY/
# SUBINDUSTRY so the grid search has variety to sweep.
SEED_EXPRESSIONS = [
    # Short-term cross-sectional reversal (overreaction snaps back).
    "group_neutralize(rank(-1 * ts_delta(close, 5)), SECTOR)",
    # Intermediate time-series momentum (trend persistence).
    "group_neutralize(ts_rank(ts_delta(close, 60), 240), INDUSTRY)",
    # Low-volatility factor (prefer low realized vol).
    "group_neutralize(rank(-1 * ts_std_dev(returns, 60)), SECTOR)",
    # Risk-adjusted momentum (Sharpe-like: mean return per unit of vol).
    "group_neutralize(rank(ts_mean(returns, 20) / ts_std_dev(returns, 60)), SUBINDUSTRY)",
    # Volume-price divergence -> reversal.
    "group_neutralize(rank(-1 * ts_corr(close, volume, 20)), INDUSTRY)",
    # Reversal weighted by recent volume (high-attention names mean-revert).
    "group_neutralize(rank(-1 * ts_delta(close, 5) * ts_rank(volume, 20)), SECTOR)",
    # VWAP mean reversion.
    "group_neutralize(rank(-1 * (vwap - ts_mean(vwap, 20))), SECTOR)",
    # Earnings yield (value/quality, fundamental).
    "group_neutralize(rank(est_eps / close), INDUSTRY)",
    # Decay-smoothed momentum (linear-weighted to cut noise).
    "group_neutralize(ts_rank(ts_decay_linear(ts_delta(close, 10), 10), 60), SECTOR)",
    # Cross-sectional z-score reversal on returns.
    "group_neutralize(rank(-1 * ts_zscore(returns, 20)), SUBINDUSTRY)",
]

# Curated earnings4 battery -- used ONLY when the engine is scoped to earnings4
# (config.WQ_DATASET_ID == "earnings4"); the generic factor-zoo seeds above are
# untouched and still used for every other (unscoped) run. Hand-built from the
# dataset's documented "most loaded objects" (see the "Earnings4 Dedicated Miner"
# strategy doc): xern spreads (implied earnings effect), realised earnings-vol
# share, forecast-vs-implied gap, PEAD, term-structure snapshots, a vector_neut
# residual, and an ex-earnings vol risk premium. VECTOR fields are reduced with
# vec_avg; sparse forecast/event fields are backfilled; all industry-neutral per
# the dataset's usage advice. Stored UNSCORED -> the orchestrator MUST simulate
# them (no fabricated metrics); a field/typing mismatch surfaces as a sim error.
EARNINGS4_SEED_EXPRESSIONS = [
    # Rebuilt against the LIVE earnings4 vocabulary. The API returns DESCRIPTIVE
    # ids -- pct_move_announcement_N, best_fit_implied_announcement_effect,
    # aggregate_option_open_interest, eighth_event_option_effect, ... -- NOT the
    # ern4_* shorthand the previous battery hardcoded, so every old seed pointed
    # at a non-existent field and was dropped UNSCORED (15/15). These use only
    # CONFIRMED live ids (dense MATRIX fields -> no vec_avg / backfill needed);
    # industry-neutral per the dataset doc, with a few SECTOR/SUBINDUSTRY for the
    # grid sweep. The _unknown_fields() guard in main() additionally drops any
    # seed whose fields are absent from data_fields.json, so a stale id can never
    # silently waste a simulation slot again. Add more shapes once the full live
    # field list is dumped.
    # 1. PEAD overreaction reversal on the latest event move.
    "group_neutralize(-rank(pct_move_announcement_1), INDUSTRY)",
    # 2. Event reaction normalised by the typical reaction (earnings fingerprint).
    "group_neutralize(divide(pct_move_announcement_1, absolute_average_announcement_percent_move), INDUSTRY)",
    # 3. Consecutive-event move spread (reaction acceleration / fade).
    "group_neutralize(rank(subtract(pct_move_announcement_1, pct_move_announcement_2)), INDUSTRY)",
    # 4. Implied announcement effect LEVEL (the best earnings-field shape in gen 0).
    "group_neutralize(ts_zscore(best_fit_implied_announcement_effect, 180), SECTOR)",
    # 5. Implied announcement effect revision / drift.
    "group_neutralize(rank(ts_delta(best_fit_implied_announcement_effect, 22)), INDUSTRY)",
    # 6. Forecast-vs-realised gap: implied effect minus historical move (VRP-like).
    "group_neutralize(subtract(best_fit_implied_announcement_effect, eighth_historical_announcement_percent_move), INDUSTRY)",
    # 7. Option open-interest regime (the single best-Sharpe field in the run).
    "group_neutralize(ts_zscore(aggregate_option_open_interest, 60), SUBINDUSTRY)",
    # 8. Per-event option effect level.
    "group_neutralize(ts_zscore(eighth_event_option_effect, 180), SUBINDUSTRY)",
    # 9. Reaction gated to fire only in an elevated open-interest regime (turnover lever).
    "group_neutralize(trade_when(ts_zscore(aggregate_option_open_interest, 20) > 1, rank(pct_move_announcement_1), -1), INDUSTRY)",
]


_GROUP_TOKENS = {"SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"}


def _expr_tokens(expr):
    out, cur = [], []
    for ch in (expr or ""):
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _live_field_ids():
    """Field ids in the harvested catalog (data_fields.json). Empty set when the
    catalog is missing -> the guard below is skipped (fail-open)."""
    try:
        rows = json.loads(Path(config.FIELD_CATALOG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return set()
    if not isinstance(rows, list):
        return set()
    return {r.get("id") for r in rows if isinstance(r, dict) and r.get("id")}


def _unknown_fields(expr, known_fields, operators):
    """Field-like tokens in expr that are absent from the live catalog. Operators,
    neutralization groups and numeric literals are ignored. Returns [] when the
    catalog is unavailable, so a fresh checkout is never blocked."""
    if not known_fields:
        return []
    bad = []
    for tok in _expr_tokens(expr):
        if not tok or tok[0].isdigit():
            continue
        if tok in operators or tok in _GROUP_TOKENS:
            continue
        # A bare lower-case / snake_case identifier here is a data field id.
        if tok.islower() or "_" in tok:
            if tok not in known_fields and tok not in bad:
                bad.append(tok)
    return bad


def main():
    db = DatabaseManager()
    db.init_db_sync()
    added = 0
    # Use the curated earnings4 battery when the engine is scoped to earnings4;
    # otherwise the generic factor-zoo seeds above (unchanged behaviour).
    seeds = (EARNINGS4_SEED_EXPRESSIONS
             if getattr(config, "WQ_DATASET_ID", "") == "earnings4"
             else SEED_EXPRESSIONS)
    # Drop seeds that reference a field absent from the LIVE catalog BEFORE they
    # waste a simulation slot. The old ern4_* battery failed silently this way:
    # every id was non-existent, so all 15 seeds landed UNSCORED. Fail-open when
    # data_fields.json is missing (operators.json is required either way).
    known_fields = _live_field_ids()
    try:
        operators = set(config.ALLOWED_OPERATORS)
    except Exception:
        operators = set()
    try:
        for expr in seeds:
            missing = _unknown_fields(expr, known_fields, operators)
            if missing:
                print(f"Skipping seed (fields not in live catalog {missing}): {expr}")
                continue
            ok, canonical = SyntaxValidator.parse_and_validate(expr)
            if not ok:
                print(f"Skipping invalid seed: {expr}")
                continue
            db.insert_seed_sync(canonical, config.UNIVERSES[0], config.DECAYS[0])
            added += 1
            print(f"Seeded (unscored): {canonical}")
    finally:
        db.close_sync()
    print(f"Inserted {added} unscored seed(s). Run orchestrator.py to evaluate them.")


if __name__ == "__main__":
    main()