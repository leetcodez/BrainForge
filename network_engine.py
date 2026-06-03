import asyncio
import email.utils
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from curl_cffi import requests
from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    def __init__(self, min_delay: float, max_delay: float):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    def _jitter(self) -> float:
        mean = (self.max_delay + self.min_delay) / 2
        std_dev = max(0.001, (self.max_delay - self.min_delay) / 4)
        return max(self.min_delay, min(self.max_delay, random.gauss(mean, std_dev)))

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_at:
                await asyncio.sleep(self._next_allowed_at - now)
            self._next_allowed_at = time.monotonic() + self._jitter()

    async def defer(self, delay: float):
        async with self._lock:
            self._next_allowed_at = max(self._next_allowed_at, time.monotonic() + delay)


class NetworkEngine:
    def __init__(self):
        self._auth_lock = asyncio.Lock()
        self._rate_limiter = AsyncRateLimiter(config.MIN_JITTER_SECS, config.MAX_JITTER_SECS)
        self.cookie = self._load_cookie()
        self.session = self._create_session(self.cookie)

    @staticmethod
    def _load_cookie() -> str:
        load_dotenv(override=True)
        return os.getenv("WQ_COOKIE") or config.WQ_COOKIE

    @staticmethod
    def _create_session(cookie: str):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        else:
            logger.warning("WQ_COOKIE is empty. Authenticated WorldQuant requests will fail until .env is updated.")

        return requests.AsyncSession(
            impersonate=config.BROWSER_IMPERSONATE,
            headers=headers,
        )

    async def _replace_session(self, cookie: str):
        old_session = self.session
        self.cookie = cookie
        self.session = self._create_session(cookie)
        if old_session:
            await old_session.close()

    async def _refresh_auth_loop(self, failed_cookie: str):
        """Wait for WQ_COOKIE to change in .env, then rebuild only this engine's session."""
        async with self._auth_lock:
            if self.cookie != failed_cookie:
                return

            new_cookie = self._load_cookie()
            if new_cookie and new_cookie != self.cookie:
                logger.info("New cookie detected. Re-initializing WorldQuant session.")
                await self._replace_session(new_cookie)
                return

            logger.error("AUTHENTICATION EXPIRED. Waiting for WQ_COOKIE update in .env...")
            old_cookie = self.cookie
            while True:
                await asyncio.sleep(5)
                new_cookie = self._load_cookie()
                if new_cookie and new_cookie != old_cookie:
                    logger.info("New cookie detected. Re-initializing WorldQuant session.")
                    await self._replace_session(new_cookie)
                    return

    @staticmethod
    def _parse_retry_after(raw_value: Optional[str]) -> Optional[float]:
        if not raw_value:
            return None
        try:
            return float(raw_value)
        except ValueError:
            try:
                parsed_date = email.utils.parsedate_to_datetime(raw_value)
                now = datetime.now(timezone.utc)
                delay = (parsed_date - now).total_seconds()
                return max(0.0, delay)
            except (TypeError, ValueError):
                return None

    async def _handle_rate_limit(self, response: requests.Response) -> bool:
        if response.status_code != 429:
            return False

        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
        delay = retry_after if retry_after is not None else config.MAX_JITTER_SECS * 2
        logger.warning(f"Rate limited (429). Retrying after {delay} seconds.")
        await self._rate_limiter.defer(delay)
        await asyncio.sleep(delay)
        return True

    async def request(self, method: str, endpoint: str, json: Optional[Dict] = None, retry_count: int = 15) -> Dict[str, Any]:
        url = endpoint if endpoint.startswith("http") else f"{config.WQ_BASE_URL}{endpoint}"

        for attempt in range(retry_count):
            await self._rate_limiter.wait()
            try:
                response = await self.session.request(method, url, json=json)

                if response.status_code in (401, 403):
                    await self._refresh_auth_loop(self.cookie)
                    continue

                if await self._handle_rate_limit(response):
                    continue

                if response.status_code >= 400:
                    logger.error(f"HTTP {response.status_code} Error: {response.text}")
                    response.raise_for_status()

                result: Dict[str, Any] = {}
                if response.text.strip():
                    try:
                        result = response.json()
                    except Exception as parse_e:
                        logger.warning(f"Failed to parse JSON response: {parse_e}")

                for key, value in response.headers.items():
                    if key.lower() == "location":
                        result["Location"] = value
                    else:
                        result[key] = value

                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is not None:
                    await self._rate_limiter.defer(retry_after)

                return result

            except Exception as e:
                logger.error(f"Request failed: {url} - {e}")
                if attempt == retry_count - 1:
                    raise
                await self._rate_limiter.defer(config.MAX_JITTER_SECS)
                await asyncio.sleep(config.MAX_JITTER_SECS)

        raise Exception(f"Failed to fetch {url} after {retry_count} attempts.")

    async def close(self):
        if self.session:
            await self.session.close()
