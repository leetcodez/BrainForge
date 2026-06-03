import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ELITE_SEEDS = [
    "group_neutralize(ts_mean(implied_volatility_call_30 - implied_volatility_put_30, 3), bucket(rank(cap), range='0,1,0.1'))",
    "group_neutralize(ts_decay_linear(group_rank(-1 * ts_delta(ts_backfill(mdl53_jc5_5year, 2) - ts_backfill(mdl53_jc5_1year, 2), 5), market) / ts_std_dev(returns, 9), 10), subindustry)"
]

def inject_seeds():
    conn = sqlite3.connect("brain_memory.db")
    cursor = conn.cursor()
    
    injected_count = 0
    
    for expression in ELITE_SEEDS:
        try:
            cursor.execute('''
                INSERT INTO alpha_population (expression, alpha_id, generation, sharpe, turnover, fitness, ast_depth, is_tuned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (expression, "MANUAL_SEED", 0, 2.50, 0.10, 5.0, 5, 1))
            injected_count += 1
            logger.info(f"Injected: {expression[:50]}...")
        except sqlite3.IntegrityError:
            logger.warning(f"Duplicate, skipping: {expression[:50]}...")
        except Exception as e:
            logger.error(f"Injection failed: {e}")
            
    conn.commit()
    conn.close()
    print(f"\n[+] Injected {injected_count} elite seeds.")

if __name__ == "__main__":
    inject_seeds()
