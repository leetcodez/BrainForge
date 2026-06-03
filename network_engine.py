import asyncio
import time
import random
import logging
import re
from typing import Dict, Any, Optional
from curl_cffi import requests

import config

logger = logging.getLogger(__name__)

class NetworkEngine:
    def __init__(self):
        jwt_token = None
        match = re.search(r't=([a-zA-Z0-9\.\-_]+)', config.WQ_COOKIE)
        if match:
            jwt_token = match.group(1)
        
        headers = {
            "Content-Type": "application/json"
        }
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        else:
            headers["Cookie"] = config.WQ_COOKIE
            logger.warning("Falling back to raw cookie auth.")
            
        self.session = requests.AsyncSession(
            impersonate=config.BROWSER_IMPERSONATE,
            headers=headers
        )

    async def _gaussian_jitter(self):
        mean = (config.MAX_JITTER_SECS + config.MIN_JITTER_SECS) / 2
        std_dev = (config.MAX_JITTER_SECS - config.MIN_JITTER_SECS) / 4
        delay = max(config.MIN_JITTER_SECS, min(config.MAX_JITTER_SECS, random.gauss(mean, std_dev)))
        await asyncio.sleep(delay)

    async def _handle_rate_limit(self, response: requests.Response) -> bool:
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else config.MAX_JITTER_SECS * 2
            logger.warning(f"Rate limited (429). Retrying after {delay} seconds.")
            await asyncio.sleep(delay)
            return True
        return False

    async def request(self, method: str, endpoint: str, json: Optional[Dict] = None, retry_count: int = 3) -> Dict[str, Any]:
        url = f"{config.WQ_BASE_URL}{endpoint}"
        
        for attempt in range(retry_count):
            await self._gaussian_jitter()
            try:
                response = await self.session.request(method, url, json=json)
                
                if await self._handle_rate_limit(response):
                    continue
                
                if response.status_code >= 400:
                    logger.error(f"HTTP {response.status_code} Error: {response.text}")
                    response.raise_for_status()

                result = {}
                if response.text.strip():
                    try:
                        result = response.json()
                    except Exception as parse_e:
                        logger.warning(f"Failed to parse JSON response: {parse_e}")
                
                for k, v in response.headers.items():
                    if k.lower() == 'location':
                        result['Location'] = v
                    else:
                        result[k] = v
                        
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    await asyncio.sleep(float(retry_after))

                return result
                
            except Exception as e:
                logger.error(f"Request failed: {url} - {e}")
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(config.MAX_JITTER_SECS)
                
        raise Exception(f"Failed to fetch {url} after {retry_count} attempts.")

    async def close(self):
        await self.session.close()
