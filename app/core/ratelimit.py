import time
from collections import deque
from collections.abc import Callable

from fastapi import Request


class RateLimited(Exception):
    """A visitor is over the hourly limit, or the daily question cap is reached."""


class RateLimiter:
    """Sliding-window limiter, in memory. Keys (visitor IPs) are never logged or stored."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        self._prune(now)
        hits = self._hits.setdefault(key, deque())
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]


def client_key(request: Request) -> str:
    """The visitor behind the proxy: first X-Forwarded-For hop, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"
