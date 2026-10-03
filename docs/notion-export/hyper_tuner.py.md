```python
import asyncio
import logging

import optuna

import config
from orchestrator import AlphaFactory, _ast_depth
from syntax_validator import SyntaxValidator

logger = logging.getLogger(__name__)

# Standalone hyperparameter tuner. This is NOT part of the genetic loop -- run it
# manually to refine a single promising template. It reuses the orchestrator's
# exact simulation path (AlphaFactory._simulate_alpha) so tuned scores are
# directly comparable to a normal factory run, and benefits from the same
# result cache / rate limiting / auth handling.

BASE_TEMPLATE = (
    "group_neutralize(rank(ts_zscore({PRICE}, {LOOKBACK_LONG}) * "
    "ts_delta({PRICE}, {LOOKBACK_SHORT})), {NEUTRALIZATION})"
)


def _build_expression(trial) -> str:
    price = trial.suggest_categorical("price", config.PRICE_FIELDS)
    lookback_short = trial.suggest_int("lookback_short", 5, 30)
    lookback_long = trial.suggest_int("lookback_long", 40, 252)
    neutralization = trial.suggest_categorical("neutralization", config.NEUTRALIZATIONS)
    return (
        BASE_TEMPLATE
        .replace("{PRICE}", price)
        .replace("{LOOKBACK_LONG}", str(lookback_long))
        .replace("{LOOKBACK_SHORT}", str(lookback_short))
        .replace("{NEUTRALIZATION}", neutralization)
    )


async def _run(n_trials: int):
    factory = AlphaFactory()
    await factory.initialize()
    study = optuna.create_study(direction="maximize")
    try:
        for _ in range(n_trials):
            trial = study.ask()
            raw = _build_expression(trial)
            universe = trial.suggest_categorical("universe", config.UNIVERSES)
            decay = trial.suggest_categorical("decay", config.DECAYS)
            ok, expression = SyntaxValidator.parse_and_validate(raw)
            if not ok:
                study.tell(trial, float("-inf"))
                continue
            result = await factory._simulate_alpha(expression, universe, decay)
            score = result.sharpe if result.valid else float("-inf")
            if result.valid:
                # Persist tuned alphas (is_tuned=1) so the work isn't discarded;
                # is_qualified stays 0 so the tuner never auto-submits.
                await factory.db.save_alpha(
                    result.expression, result.universe, result.decay, result.alpha_id,
                    -1, result.sharpe, result.turnover, score,
                    _ast_depth(result.expression), result.skew, result.kurtosis,
                    result.track_record_length, None, is_tuned=1,
                    returns=result.returns, oos_sharpe=result.oos_sharpe,
                )
            study.tell(trial, score)
            logger.info(f"trial sharpe={score:.3f} expr={expression}")
        print("Best params:", study.best_params)
        print("Best sharpe:", study.best_value)
    finally:
        await factory.shutdown()


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run(n_trials=30))


if __name__ == "__main__":
    main()
```