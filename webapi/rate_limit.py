"""
Lightweight, dependency-free rate limiting and brute-force protection shared
between webapi/server.py (REST) and webapi/events.py (websocket) - one
instance of each class is created in start_peer.py and passed to both, so an
attacker hammering one surface gets blocked on the other too.

No new dependency: this is a hackathon-scale threat model (single local
process, no distributed rate-limit state needed), a full library like
Flask-Limiter would be overkill for what's just a few dicts behind a lock.
"""
import threading
import time


class RateLimiter:
    """Sliding-window request cap per key (e.g. client IP)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, [])
            cutoff = now - self.window
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True


class FailedAuthTracker:
    """
    Blocks a key (client IP) for `block_seconds` after `max_failures` bad
    auth attempts within `window_seconds`. This is the brute-force /
    token-guessing deterrent - logs loudly so it's visible live (also makes
    a decent demo moment: PS3's "additional security mechanisms" bonus).
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 60, block_seconds: float = 300):
        self.max_failures = max_failures
        self.window = window_seconds
        self.block_seconds = block_seconds
        self._failures: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            until = self._blocked_until.get(key)
            if until is None:
                return False
            if time.monotonic() < until:
                return True
            del self._blocked_until[key]
            return False

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._failures.setdefault(key, [])
            cutoff = now - self.window
            while hits and hits[0] < cutoff:
                hits.pop(0)
            hits.append(now)
            if len(hits) >= self.max_failures:
                self._blocked_until[key] = now + self.block_seconds
                self._failures[key] = []
                print(f"\n[SECURITY] {key} blocked for {self.block_seconds:.0f}s after {len(hits)} failed auth attempts\n", flush=True)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
