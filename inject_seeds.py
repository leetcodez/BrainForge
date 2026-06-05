import config
from db_manager import DatabaseManager
from syntax_validator import SyntaxValidator

# Hand-curated seed expressions. They are stored UNSCORED (sharpe = NULL) so the
# orchestrator MUST actually simulate them before trusting them -- we never
# fabricate metrics for a seed. Requires operators.json to exist (run
# probe_wq.py first) so the validator can check operator names/arity.
SEED_EXPRESSIONS = [
    "group_neutralize(rank(ts_zscore(close, 120)), SECTOR)",
    "group_neutralize(ts_rank(ts_delta(close, 5), 60), INDUSTRY)",
    "group_neutralize(rank(ts_mean(returns, 20) / ts_std_dev(returns, 60)), SECTOR)",
    "group_neutralize(rank(ts_delta(est_eps, 22)), SUBINDUSTRY)",
]


def main():
    db = DatabaseManager()
    db.init_db_sync()
    added = 0
    try:
        for expr in SEED_EXPRESSIONS:
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