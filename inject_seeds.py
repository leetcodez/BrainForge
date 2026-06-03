import sqlite3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# List of elite hand-crafted alphas to inject
ELITE_SEEDS = [
    "group_neutralize(rank(ts_decay_linear(close, 20)), SUBINDUSTRY)",
    "group_neutralize(rank(ts_mean(volume, 60)), SUBINDUSTRY)",
    # Paste your actual alpha strings here
]

def inject_seeds():
    """Injects manually curated elite alphas into the database with high performance metrics."""
    conn = sqlite3.connect("brain_memory.db")
    cursor = conn.cursor()
    
    injected_count = 0
    
    for expression in ELITE_SEEDS:
        try:
            # Metrics hardcoded to elite levels to force NSGA-II selection
            cursor.execute('''
                INSERT INTO alpha_population (expression, alpha_id, generation, sharpe, turnover, fitness, ast_depth, is_tuned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (expression, "MANUAL_SEED", 0, 2.50, 0.10, 5.0, 5, 1))
            injected_count += 1
            logger.info(f"Successfully injected seed: {expression[:50]}...")
        except sqlite3.IntegrityError:
            logger.warning(f"Seed already exists, skipping: {expression[:50]}...")
        except Exception as e:
            logger.error(f"Failed to inject seed: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"\n[+] Seed Injection Complete. Successfully injected {injected_count} elite seeds.")

if __name__ == "__main__":
    inject_seeds()
