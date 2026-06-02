import sqlite3
import asyncio
import logging
from curl_cffi import requests

# Reuse configuration and network engine
import config
from network_engine import NetworkEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def submit_to_portfolio():
    """Selects high-performing alphas and submits them to the WorldQuant API."""
    conn = sqlite3.connect("brain_memory.db")
    cursor = conn.cursor()
    
    # Query for expressions that meet performance criteria and have an alpha_id
    cursor.execute('''
        SELECT expression, alpha_id FROM alpha_population 
        WHERE sharpe >= 1.25 AND turnover <= 0.70 AND alpha_id IS NOT NULL AND alpha_id != ''
    ''')
    winning_alphas = cursor.fetchall()
    conn.close()

    if not winning_alphas:
        logger.info("No qualifying alphas found in database.")
        return

    network = NetworkEngine()
    
    logger.info(f"Found {len(winning_alphas)} candidate alphas for submission.")

    for expression, alpha_id in winning_alphas:
        logger.info(f"Submitting Alpha [{alpha_id}]: {expression}")
        
        try:
            # Send the submission POST request
            response = await network.request("POST", f"/alphas/{alpha_id}/submit")
            
            # Check for failure in response text or status
            # The API often returns {"is": {...}} on success, or an error/status indicating failure
            # If the network_engine returned the JSON dict, we can inspect it:
            if "SELF_CORRELATION" in str(response):
                logger.warning(f"❌ Rejected: High Auto-Correlation for [{alpha_id}]")
            elif response.get("status") == "ERROR":
                logger.warning(f"❌ Submission Failed for [{alpha_id}]: {response}")
            else:
                logger.info(f"✅ Successfully submitted to IQC Portfolio: [{alpha_id}]")
                
        except Exception as e:
            if "SELF_CORRELATION" in str(e):
                logger.warning(f"❌ Rejected: High Auto-Correlation for [{alpha_id}]")
            else:
                logger.error(f"Submission failed for [{alpha_id}]: {e}")

    await network.close()

if __name__ == "__main__":
    asyncio.run(submit_to_portfolio())
