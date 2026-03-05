"""Throttling classes matching DRF's throttle API."""

from __future__ import annotations

import time
from typing import Any


class BaseThrottle:
    """Base class for throttle backends."""

    def allow_request(self, request: Any, view: Any) -> bool:
        raise NotImplementedError

    def wait(self) -> float | None:
        """Return the number of seconds to wait before the next request, or None."""
        return None

    def get_ident(self, request: Any) -> str:
        """Return a unique identifier for the request (IP-based by default)."""
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        client = getattr(request, "client", None)
        if client:
            host = getattr(client, "host", None)
            if host:
                return host
        return "unknown"


class SimpleRateThrottle(BaseThrottle):
    """Throttle that limits requests using a simple rate string like '100/hour'.

    Subclasses must set `rate` (e.g. '10/minute') or `THROTTLE_RATES`
    and implement `get_cache_key(request, view)`.
    """

    cache: dict[str, list[float]] = {}
    rate: str | None = None
    scope: str | None = None
    THROTTLE_RATES: dict[str, str] = {}

    RATE_DURATIONS: dict[str, int] = {
        "s": 1,
        "sec": 1,
        "m": 60,
        "min": 60,
        "h": 3600,
        "hour": 3600,
        "d": 86400,
        "day": 86400,
    }

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own cache
        cls.cache = {}

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        raise NotImplementedError

    def get_rate(self) -> str:
        if self.rate:
            return self.rate
        if self.scope and self.scope in self.THROTTLE_RATES:
            return self.THROTTLE_RATES[self.scope]
        raise ValueError(
            f"No rate set for {self.__class__.__name__}. "
            "Set `rate` or add the scope to `THROTTLE_RATES`."
        )

    def parse_rate(self, rate: str) -> tuple[int, int]:
        """Parse a rate string like '10/minute' into (num_requests, duration_seconds)."""
        num, period = rate.split("/")
        num_requests = int(num)
        duration = self.RATE_DURATIONS.get(period, None)
        if duration is None:
            raise ValueError(f"Unknown rate period: {period!r}")
        return num_requests, duration

    def allow_request(self, request: Any, view: Any) -> bool:
        key = self.get_cache_key(request, view)
        if key is None:
            return True

        rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(rate)

        now = time.time()
        history = self.cache.get(key, [])

        # Drop entries outside the window
        while history and history[0] <= now - self.duration:
            history.pop(0)

        if len(history) >= self.num_requests:
            self.cache[key] = history
            return False

        history.append(now)
        self.cache[key] = history
        return True

    def wait(self) -> float | None:
        if not hasattr(self, "duration") or not hasattr(self, "num_requests"):
            return None
        # No meaningful wait if we don't know the history
        return self.duration / self.num_requests


class AnonRateThrottle(SimpleRateThrottle):
    """Throttle unauthenticated requests by IP."""

    scope: str = "anon"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        if request.user is not None:
            return None  # Only throttle anonymous users
        return f"throttle_{self.scope}_{self.get_ident(request)}"


class UserRateThrottle(SimpleRateThrottle):
    """Throttle authenticated requests by user ID, anonymous by IP."""

    scope: str = "user"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        if request.user is not None:
            user_id = getattr(request.user, "id", None) or getattr(request.user, "pk", None) or str(request.user)
            return f"throttle_{self.scope}_{user_id}"
        return f"throttle_{self.scope}_{self.get_ident(request)}"
