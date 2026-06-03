import sqlite3
import asyncio
import logging
from curl_cffi import requests

import config
from network_engine import NetworkEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def submit_to_portfolio():
    conn = sqlite3.connect("brain_memory.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT expression, alpha_id FROM alpha_population 
        WHERE sharpe >= 1.25 AND turnover <= 0.70 AND alpha_id IS NOT NULL AND alpha_id != '' AND alpha_id != 'MANUAL_SEED'
    ''')
    winning_alphas = cursor.fetchall()
    conn.close()

    if not winning_alphas:
        logger.info("No qualifying alphas found.")
        return

    network = NetworkEngine()
    logger.info(f"Found {len(winning_alphas)} candidates for submission.")

    for expression, alpha_id in winning_alphas:
        logger.info(f"Submitting Alpha [{alpha_id}]: {expression}")
        
        try:
            response = await network.request("POST", f"/alphas/{alpha_id}/submit")
            
            if "SELF_CORRELATION" in str(response):
                logger.warning(f"❌ Rejected: High Auto-Correlation [{alpha_id}]")
            elif response.get("status") == "ERROR":
                logger.warning(f"❌ Submission Failed [{alpha_id}]: {response}")
            else:
                logger.info(f"✅ Successfully submitted: [{alpha_id}]")
                
        except Exception as e:
            if "SELF_CORRELATION" in str(e):
                logger.warning(f"❌ Rejected: High Auto-Correlation [{alpha_id}]")
            else:
                logger.error(f"Submission failed [{alpha_id}]: {e}")

    await network.close()

if __name__ == "__main__":
    asyncio.run(submit_to_portfolio())
