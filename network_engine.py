import asyncio
import logging
import random
import time

from curl_cffi import requests
from dotenv import dotenv_values

import config

logger = logging.getLogger(__name__)


class AuthenticationError(RuntimeError):
    """Raised when the session cannot be (re)authenticated within the budget."""


class AsyncRateLimiter:
    """Global request spacer.

    Reserves the next allowed start time INSIDE the lock, then sleeps OUTSIDE
    the lock. The original implementation slept while holding the lock, which
    serialized the entire pipeline (every coroutine queued behind one sleeping
    coroutine). Here the lock is held only for microseconds.
    """

    def __init__(self, min_delay: float, max_delay: float):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    def _jitter(self) -> float:
        return random.uniform(self.min_delay, self.max_delay)

    async def wait(self):
        while True:
            async with self._lock:
                now = time.monotonic()
                if now >= self._next_allowed_at:
                    self._next_allowed_at = now + self._jitter()
                    return
                sleep_for = self._next_allowed_at - now
            await asyncio.sleep(sleep_for)

    async def defer(self, delay: float):
        """Push the next-allowed time out by `delay` (e.g. on 429/backoff)."""
        async with self._lock:
            self._next_allowed_at = max(self._next_allowed_at, time.monotonic() + delay)


class NetworkEngine:
    def __init__(self, cookie: str | None = None):
        self.cookie = cookie if cookie is not None else self._load_cookie()
        self.session = self._build_session(self.cookie)
        self._rate_limiter = AsyncRateLimiter(config.MIN_JITTER_SECS, config.MAX_JITTER_SECS)
        self._auth_lock = asyncio.Lock()

    # --- session / auth ------------------------------------------------------
    @staticmethod
    def _load_cookie() -> str:
        # Re-read .env each time so a human can refresh WQ_COOKIE without a
        # restart; falls back to the value loaded at import.
        values = dotenv_values()
        return values.get("WQ_COOKIE") or config.WQ_COOKIE or ""

    def _build_session(self, cookie: str) -> "requests.AsyncSession":
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if cookie:
            headers["Cookie"] = cookie
        return requests.AsyncSession(
            impersonate=config.BROWSER_IMPERSONATE,
            headers=headers,
            timeout=60,
        )

    async def _replace_session(self, cookie: str):
        old = self.session
        self.cookie = cookie
        self.session = self._build_session(cookie)
        try:
            await old.close()
        except Exception:
            pass

    async def _authenticate(self) -> str | None:
        """Best-effort programmatic login. Returns a cookie string or None."""
        if not (config.WQ_EMAIL and config.WQ_PASSWORD):
            return None
        auth_session = requests.AsyncSession(
            impersonate=config.BROWSER_IMPERSONATE,
            headers={"Accept": "application/json"},
            timeout=60,
        )
        try:
            resp = await auth_session.post(
                f"{config.WQ_BASE_URL}/authentication",
                auth=(config.WQ_EMAIL, config.WQ_PASSWORD),
            )
            cookie = "; ".join(f"{c.name}={c.value}" for c in auth_session.cookies)
            if resp.status_code in (200, 201) and cookie:
                logger.info("Programmatic authentication succeeded.")
                return cookie
            logger.error(f"Programmatic authentication failed: HTTP {resp.status_code}.")
            return None
        except Exception as e:
            logger.error(f"Programmatic authentication error: {e}")
            return None
        finally:
            try:
                await auth_session.close()
            except Exception:
                pass

    async def _refresh_auth(self, failed_cookie: str):
        """Bounded, non-blocking re-auth. Never loops forever.

        Order: (1) programmatic login, (2) reload .env, (3) bounded wait for a
        human to update .env (also retrying programmatic login). Raises
        AuthenticationError if nothing works within AUTH_REFRESH_MAX_WAIT_SECS.
        """
        async with self._auth_lock:
            # Another coroutine may have already refreshed while we waited.
            if self.cookie != failed_cookie:
                return

            new_cookie = await self._authenticate()
            if new_cookie:
                await self._replace_session(new_cookie)
                return

            env_cookie = self._load_cookie()
            if env_cookie and env_cookie != failed_cookie:
                logger.info("Loaded a refreshed cookie from .env.")
                await self._replace_session(env_cookie)
                return

            logger.error(
                "AUTH EXPIRED. Set WQ_EMAIL/WQ_PASSWORD for auto-login or update "
                "WQ_COOKIE in .env. Waiting up to %ss...",
                config.AUTH_REFRESH_MAX_WAIT_SECS,
            )
            deadline = time.monotonic() + config.AUTH_REFRESH_MAX_WAIT_SECS
            while time.monotonic() < deadline:
                await asyncio.sleep(5)
                env_cookie = self._load_cookie()
                if env_cookie and env_cookie != failed_cookie:
                    await self._replace_session(env_cookie)
                    return
                new_cookie = await self._authenticate()
                if new_cookie:
                    await self._replace_session(new_cookie)
                    return
            raise AuthenticationError("Could not refresh authentication within the time budget.")

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _safe_json(response):
        try:
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _parse_retry_after(value) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_result(response) -> dict:
        headers = {k: v for k, v in response.headers.items()}
        location = None
        for key, val in response.headers.items():
            if key.lower() == "location":
                location = val
                break
        return {
            "status_code": response.status_code,
            "headers": headers,
            "location": location,
            "json": NetworkEngine._safe_json(response),  # dict | list | None
        }

    # --- core request --------------------------------------------------------
    async def request(self, method: str, endpoint: str, json=None) -> dict:
        """Perform a request and return a structured result dict:
            {status_code, headers, location, json}

        Retry policy:
          * transport errors and 5xx  -> retry, consuming the error budget
          * 401/403                    -> refresh auth, retry (no budget cost)
          * 429                        -> honor Retry-After, retry (no budget cost)
          * other 4xx                  -> TERMINAL, returned to caller (no retry)
        """
        url = endpoint if endpoint.startswith("http") else f"{config.WQ_BASE_URL}{endpoint}"
        error_retries = 0
        auth_retries = 0

        while True:
            await self._rate_limiter.wait()
            current_cookie = self.cookie
            try:
                response = await self.session.request(method, url, json=json)
            except Exception as e:
                error_retries += 1
                logger.error(f"Transport error on {method} {url}: {e} "
                             f"(retry {error_retries}/{config.NETWORK_MAX_ERROR_RETRIES})")
                if error_retries >= config.NETWORK_MAX_ERROR_RETRIES:
                    raise
                await self._rate_limiter.defer(config.MAX_JITTER_SECS)
                await asyncio.sleep(config.MAX_JITTER_SECS)
                continue

            status = response.status_code

            if status in (401, 403):
                auth_retries += 1
                if auth_retries > config.AUTH_MAX_REFRESH_ATTEMPTS:
                    # Bounded: a login that "succeeds" but keeps yielding a
                    # rejected cookie must not loop forever.
                    raise AuthenticationError(
                        f"Still unauthorized after {auth_retries - 1} refresh attempt(s)."
                    )
                logger.warning(f"Auth required ({status}) on {url}; refreshing session "
                               f"(attempt {auth_retries}/{config.AUTH_MAX_REFRESH_ATTEMPTS}).")
                await self._refresh_auth(current_cookie)
                continue

            if status == 429:
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                backoff = retry_after if retry_after is not None else config.MAX_JITTER_SECS * 2
                logger.warning(f"Throttled (429) on {url}; backing off {backoff:.1f}s.")
                await self._rate_limiter.defer(backoff)
                await asyncio.sleep(backoff)
                continue

            if 400 <= status < 500:
                # Terminal client error (e.g. malformed expression). Do NOT
                # retry; hand the structured result back so the caller decides.
                logger.error(f"Client error {status} on {method} {url}: {str(response.text)[:300]}")
                return self._build_result(response)

            if status >= 500:
                error_retries += 1
                logger.error(f"Server error {status} on {url} "
                             f"(retry {error_retries}/{config.NETWORK_MAX_ERROR_RETRIES})")
                if error_retries >= config.NETWORK_MAX_ERROR_RETRIES:
                    return self._build_result(response)
                await self._rate_limiter.defer(config.MAX_JITTER_SECS)
                await asyncio.sleep(config.MAX_JITTER_SECS)
                continue

            # 2xx / 3xx success. A Retry-After here (used by WQ while a
            # simulation is still computing) just paces the next poll.
            retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
            if retry_after:
                await self._rate_limiter.defer(retry_after)
            return self._build_result(response)

    async def close(self):
        try:
            await self.session.close()
        except Exception:
            pass