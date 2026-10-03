import asyncio
import base64
import json
import logging
import random
import time
from pathlib import Path

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
    def __init__(self, cookie: str | None = None, on_auth_required=None):
        # Epoch seconds at which the current cookie expires (None = unknown).
        self._cookie_expiry = None
        self.cookie = cookie if cookie is not None else self._load_cookie()
        self.session = self._build_session(self.cookie)
        self._rate_limiter = AsyncRateLimiter(config.MIN_JITTER_SECS, config.MAX_JITTER_SECS)
        self._auth_lock = asyncio.Lock()
        # Programmatic-login rate limiting (runaway sign-in guard). Tracks recent
        # _authenticate() timestamps and trips a circuit breaker when WorldQuant's
        # rolling sign-in cap is approached, so a login -> still-401 -> login loop
        # can no longer lock the account out.
        self._login_attempt_times = []
        self._auth_circuit_open = False
        # Invoked ONCE when a forced re-auth needs the human (face-ID). Defaults
        # to a prominent banner + sentinel file; the factory can override it to
        # push an alert elsewhere.
        self.on_auth_required = on_auth_required or self._default_auth_notification
        self._keepalive_task = None

    # --- session / auth ------------------------------------------------------
    @staticmethod
    def _read_env_cookie() -> str:
        """Read WQ_COOKIE fresh from .env (falling back to the import-time config
        value). dotenv_values re-reads the file on every call, so a human can
        paste a new cookie without restarting the process."""
        values = dotenv_values()
        return values.get("WQ_COOKIE") or config.WQ_COOKIE or ""

    @staticmethod
    def _cookie_expiry_from_jwt(cookie: str):
        """Best-effort decode of the `t=` JWT's `exp` claim -> epoch seconds.
        Returns None when the token is absent/unparseable so callers degrade
        gracefully. NOTE: a still-future `exp` does NOT prove the session is
        live -- the server can invalidate a cookie whose JWT has not expired."""
        if not cookie:
            return None
        token = None
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("t="):
                token = part[2:]
                break
        if not token:
            return None
        try:
            segments = token.split(".")
            if len(segments) < 2:
                return None
            payload_b64 = segments[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            return float(exp) if exp is not None else None
        except Exception:
            return None

    def _load_cookie(self) -> str:
        # Precedence matters. A cookie the human just pasted into .env ALWAYS
        # wins over the cached session, because the only reason to paste a fresh
        # one is that the cached cookie died (e.g. server-side invalidation,
        # which a still-future JWT `exp` does NOT reveal). This prevents a stale
        # .wq_session.json from permanently shadowing fresh credentials across
        # restarts.
        env_cookie = self._read_env_cookie()
        cached, cached_expiry = self._load_cached_session()
        if env_cookie and env_cookie != cached:
            self._cookie_expiry = self._cookie_expiry_from_jwt(env_cookie)
            return env_cookie
        # Otherwise reuse the cached session while it is still valid. If the
        # cache did not record an expiry, derive one from the JWT so it can
        # actually age out instead of living forever.
        if cached:
            expiry = cached_expiry
            if expiry is None:
                expiry = self._cookie_expiry_from_jwt(cached)
            if expiry is None or expiry > time.time():
                self._cookie_expiry = expiry
                return cached
        self._cookie_expiry = self._cookie_expiry_from_jwt(env_cookie)
        return env_cookie

    @staticmethod
    def _load_cached_session():
        """Return (cookie, expiry_epoch) from the on-disk session cache, or
        (None, None) when absent/unreadable."""
        path = Path(config.SESSION_CACHE_PATH)
        if not path.exists():
            return None, None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None, None
        cookie = data.get("cookie") or None
        expiry = data.get("expiry")
        if expiry is not None:
            try:
                expiry = float(expiry)
            except (TypeError, ValueError):
                expiry = None
        return cookie, expiry

    @staticmethod
    def _persist_cached_session(cookie, expiry):
        try:
            Path(config.SESSION_CACHE_PATH).write_text(
                json.dumps({"cookie": cookie, "expiry": expiry}), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist session cache: {e}")

    @staticmethod
    def _earliest_expiry(cookie_jar):
        """Earliest expiry epoch across a cookie jar (None if none declare one)."""
        try:
            expiries = [c.expires for c in cookie_jar if getattr(c, "expires", None)]
            return float(min(expiries)) if expiries else None
        except Exception:
            return None

    def _cookie_expiring_soon(self) -> bool:
        if self._cookie_expiry is None:
            return False
        return time.time() >= (self._cookie_expiry - config.COOKIE_REFRESH_MARGIN_SECS)

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

    async def _replace_session(self, cookie: str, expiry=None):
        old = self.session
        self.cookie = cookie
        self._cookie_expiry = expiry
        self.session = self._build_session(cookie)
        self._persist_cached_session(cookie, expiry)
        self._clear_reauth_flag()
        try:
            await old.close()
        except Exception:
            pass

    def _login_rate_limited(self) -> bool:
        """True when a programmatic login must be SUPPRESSED -- either too soon
        after the previous attempt, or the rolling-window cap is exhausted (the
        circuit breaker). This is the guard against the login -> still-401 ->
        login loop that tripped WorldQuant's daily sign-in lockout: once the cap
        is hit we stop minting cookies and fall back to manual cookie /
        pause-and-resume."""
        now = time.monotonic()
        window = config.AUTH_LOGIN_WINDOW_SECS
        self._login_attempt_times = [t for t in self._login_attempt_times if now - t < window]
        if config.AUTH_MAX_LOGINS_PER_WINDOW <= 0:
            return True  # programmatic login disabled entirely (cookie-only mode)
        if len(self._login_attempt_times) >= config.AUTH_MAX_LOGINS_PER_WINDOW:
            if not self._auth_circuit_open:
                logger.error(
                    f"Auto-login circuit OPEN: {len(self._login_attempt_times)} "
                    f"sign-ins within {window / 3600:.1f}h hit the cap "
                    f"({config.AUTH_MAX_LOGINS_PER_WINDOW}). Suppressing programmatic "
                    "login and falling back to manual cookie / pause-and-resume to "
                    "avoid a WorldQuant account lockout.")
                self._auth_circuit_open = True
            return True
        if self._login_attempt_times:
            since = now - self._login_attempt_times[-1]
            if since < config.AUTH_MIN_LOGIN_INTERVAL_SECS:
                logger.warning(
                    f"Skipping programmatic login: only {since:.0f}s since the last "
                    f"attempt (minimum {config.AUTH_MIN_LOGIN_INTERVAL_SECS:.0f}s).")
                return True
        return False

    async def _authenticate(self):
        """Best-effort programmatic login. Returns (cookie, expiry_epoch), or
        (None, None) when unavailable/failed. The face-ID / Persona step cannot
        be performed here; this only mints a cookie when the platform accepts the
        non-interactive email/password flow."""
        if not (config.WQ_EMAIL and config.WQ_PASSWORD):
            return None, None
        if self._login_rate_limited():
            return None, None
        self._login_attempt_times.append(time.monotonic())
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
            expiry = self._earliest_expiry(auth_session.cookies)
            if resp.status_code in (200, 201) and cookie:
                logger.info("Programmatic authentication succeeded.")
                return cookie, expiry
            logger.error(f"Programmatic authentication failed: HTTP {resp.status_code}.")
            return None, None
        except Exception as e:
            logger.error(f"Programmatic authentication error: {e}")
            return None, None
        finally:
            try:
                await auth_session.close()
            except Exception:
                pass

    async def _refresh_auth(self, failed_cookie: str):
        """Re-authenticate, pausing for a human ONLY when unavoidable.

        Order:
          (1) programmatic (non-interactive) login,
          (2) a cookie refreshed out-of-band (.env or cached session file),
          (3) PAUSE + NOTIFY + WAIT for human re-auth (face-ID), then RESUME.
        Raises AuthenticationError only if the human never re-auths within
        AUTH_PAUSE_MAX_WAIT_SECS.
        """
        async with self._auth_lock:
            # Another coroutine may have already refreshed while we waited.
            if self.cookie != failed_cookie:
                return

            new_cookie, expiry = await self._authenticate()
            if new_cookie:
                await self._replace_session(new_cookie, expiry)
                return

            env_cookie = self._load_cookie()
            if env_cookie and env_cookie != failed_cookie:
                logger.info("Loaded a refreshed cookie from .env / session cache.")
                await self._replace_session(env_cookie, self._cookie_expiry)
                return

            # The face-ID / Persona step is human-only. Pause the run, notify,
            # and poll for a fresh session (auto-login OR an updated cookie) so
            # the generator RESUMES on its own once you re-auth.
            self._notify_auth_required()
            deadline = time.monotonic() + config.AUTH_PAUSE_MAX_WAIT_SECS
            while time.monotonic() < deadline:
                await asyncio.sleep(5)
                env_cookie = self._load_cookie()
                if env_cookie and env_cookie != failed_cookie:
                    logger.info("Detected a refreshed session; resuming.")
                    await self._replace_session(env_cookie, self._cookie_expiry)
                    return
                new_cookie, expiry = await self._authenticate()
                if new_cookie:
                    logger.info("Re-authenticated programmatically; resuming.")
                    await self._replace_session(new_cookie, expiry)
                    return
            raise AuthenticationError(
                "Human re-authentication did not arrive within the pause budget."
            )

    async def _try_proactive_refresh(self) -> bool:
        """Silent, NON-interactive refresh used before a known expiry. Never
        enters the human-pause path, so it can't trigger a false alarm when
        auto-login is not configured."""
        async with self._auth_lock:
            new_cookie, expiry = await self._authenticate()
            if new_cookie:
                await self._replace_session(new_cookie, expiry)
                return True
            env_cookie = self._load_cookie()
            if env_cookie and env_cookie != self.cookie:
                await self._replace_session(env_cookie, self._cookie_expiry)
                return True
            return False

    # --- human-reauth notification ------------------------------------------
    def _notify_auth_required(self):
        try:
            self.on_auth_required()
        except Exception as e:
            logger.error(f"Auth-required notification hook failed: {e}")

    def _default_auth_notification(self):
        hours = config.AUTH_PAUSE_MAX_WAIT_SECS // 3600
        banner = (
            "\n" + "=" * 72 +
            "\n  WORLDQUANT SESSION EXPIRED -- HUMAN RE-AUTH REQUIRED (face-ID)."
            "\n  The run is PAUSED and will RESUME automatically once you:"
            "\n    1. log in to WorldQuant BRAIN in your browser, then either"
            "\n    2. paste the fresh cookie into WQ_COOKIE in .env, or"
            "\n    3. leave WQ_EMAIL/WQ_PASSWORD set for auto-login."
            f"\n  Waiting up to {hours}h...\n" +
            "=" * 72
        )
        logger.warning(banner)
        try:
            Path(config.REAUTH_FLAG_PATH).write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
        try:  # audible nudge if a terminal is attached
            print("\a", end="", flush=True)
        except Exception:
            pass

    def _clear_reauth_flag(self):
        try:
            flag = Path(config.REAUTH_FLAG_PATH)
            if flag.exists():
                flag.unlink()
        except Exception:
            pass

    # --- keep-alive heartbeat ------------------------------------------------
    async def start_keepalive(self):
        if not config.KEEPALIVE_ENABLED or self._keepalive_task is not None:
            return
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def stop_keepalive(self):
        if self._keepalive_task is None:
            return
        self._keepalive_task.cancel()
        try:
            await self._keepalive_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        self._keepalive_task = None

    async def _keepalive_loop(self):
        """Periodic lightweight authenticated ping. Prevents IDLE-timeout
        logouts and proactively refreshes shortly before a known cookie expiry.
        Cannot defeat the hard face-ID limit -- that path is handled by
        _refresh_auth's pause-and-resume."""
        while True:
            try:
                await asyncio.sleep(config.KEEPALIVE_INTERVAL_SECS)
                if self._cookie_expiring_soon():
                    logger.info("Cookie nearing expiry; attempting proactive refresh.")
                    if not await self._try_proactive_refresh():
                        logger.warning(
                            "Proactive refresh unavailable; will pause-and-resume "
                            "at the next auth challenge.")
                else:
                    await self.request("GET", config.KEEPALIVE_ENDPOINT)
            except asyncio.CancelledError:
                break
            except AuthenticationError:
                logger.error("Keep-alive: re-auth pause budget exhausted; stopping heartbeat.")
                break
            except Exception as e:
                logger.warning(f"Keep-alive ping failed (non-fatal): {e}")

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
        if getattr(config,"RESEARCH_OFFLINE_ONLY",False):raise RuntimeError("Offline research mode forbids remote transport requests")
        url = endpoint if endpoint.startswith("http") else f"{config.WQ_BASE_URL}{endpoint}"
        unsafe_write=(method.upper()=="POST" and endpoint.rstrip("/").endswith("/simulations") and getattr(config,"SAFE_SIMULATION_WRITES",False))
        error_retries = 0
        auth_retries = 0
        throttle_retries = 0

        import time
        deadline=time.monotonic()+getattr(config,"NETWORK_REQUEST_TIMEOUT_SECS",120.)
        total_attempts=0
        while True:
            total_attempts+=1
            if total_attempts>getattr(config,"NETWORK_MAX_TOTAL_ATTEMPTS",20) or time.monotonic()>=deadline:
                raise TimeoutError("Network retry/deadline budget exhausted")
            await asyncio.wait_for(self._rate_limiter.wait(),timeout=max(.001,deadline-time.monotonic()))
            current_cookie = self.cookie
            try:
                response = await asyncio.wait_for(self.session.request(method,url,json=json),timeout=max(.001,deadline-time.monotonic()))
            except Exception as e:
                if unsafe_write:
                    from forge2_experiments import IndeterminateAttemptError
                    raise IndeterminateAttemptError("Simulation POST transport outcome unknown; automatic retry disabled") from e
                error_retries += 1
                logger.error(f"Transport error on {method} {url}: {e} "
                             f"(retry {error_retries}/{config.NETWORK_MAX_ERROR_RETRIES})")
                if error_retries >= config.NETWORK_MAX_ERROR_RETRIES:
                    raise
                await self._rate_limiter.defer(config.MAX_JITTER_SECS)
                await asyncio.sleep(min(config.MAX_JITTER_SECS,max(0,deadline-time.monotonic())))
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
                await asyncio.wait_for(self._refresh_auth(current_cookie),timeout=max(.001,deadline-time.monotonic()))
                continue

            if status == 429:
                throttle_retries += 1
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                if retry_after is not None:
                    backoff = retry_after
                else:
                    # Exponential backoff (capped) while the server keeps
                    # throttling, instead of poking a flat interval forever.
                    base = config.MAX_JITTER_SECS * 2
                    backoff = min(base * (2 ** (throttle_retries - 1)), config.THROTTLE_MAX_BACKOFF_SECS)
                    backoff += random.uniform(0, config.MAX_JITTER_SECS)
                logger.warning(f"Throttled (429) on {url}; backing off {backoff:.1f}s "
                               f"(throttle attempt {throttle_retries}).")
                await self._rate_limiter.defer(backoff)
                await asyncio.sleep(min(backoff,max(0,deadline-time.monotonic())))
                continue

            if 400 <= status < 500:
                # Terminal client error (e.g. malformed expression). Do NOT
                # retry; hand the structured result back so the caller decides.
                logger.error(f"Client error {status} on {method} {url}: {str(response.text)[:300]}")
                return self._build_result(response)

            if status >= 500:
                if unsafe_write:
                    from forge2_experiments import IndeterminateAttemptError
                    raise IndeterminateAttemptError("Simulation POST 5xx outcome ambiguous; automatic retry disabled")
                error_retries += 1
                logger.error(f"Server error {status} on {url} "
                             f"(retry {error_retries}/{config.NETWORK_MAX_ERROR_RETRIES})")
                if error_retries >= config.NETWORK_MAX_ERROR_RETRIES:
                    return self._build_result(response)
                await self._rate_limiter.defer(config.MAX_JITTER_SECS)
                await asyncio.sleep(min(config.MAX_JITTER_SECS,max(0,deadline-time.monotonic())))
                continue

            # 2xx / 3xx success. A Retry-After here (used by WQ while a
            # simulation is still computing) just paces the next poll.
            retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
            if retry_after:
                await self._rate_limiter.defer(retry_after)
            return self._build_result(response)

    async def close(self):
        await self.stop_keepalive()
        try:
            await self.session.close()
        except Exception:
            pass
