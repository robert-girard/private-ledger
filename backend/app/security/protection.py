from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


@dataclass(frozen=True)
class LockoutResult:
    locked: bool
    retry_after_seconds: int


class AuthProtectionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._rate_limit_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._failed_login_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lockouts: dict[str, datetime] = {}

    def reset(self) -> None:
        with self._lock:
            self._rate_limit_events.clear()
            self._failed_login_events.clear()
            self._lockouts.clear()

    def check_rate_limit(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = datetime.now(UTC)
        window = timedelta(seconds=window_seconds)
        with self._lock:
            events = self._rate_limit_events[key]
            self._prune(events, now=now, window=window)
            if len(events) >= limit:
                retry_after = max(1, int((events[0] + window - now).total_seconds()))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

            events.append(now)
            return RateLimitResult(allowed=True, retry_after_seconds=0)

    def check_lockout(self, *, key: str) -> LockoutResult:
        now = datetime.now(UTC)
        with self._lock:
            locked_until = self._lockouts.get(key)
            if locked_until is None:
                return LockoutResult(locked=False, retry_after_seconds=0)
            if locked_until <= now:
                self._lockouts.pop(key, None)
                self._failed_login_events.pop(key, None)
                return LockoutResult(locked=False, retry_after_seconds=0)

            retry_after = max(1, int((locked_until - now).total_seconds()))
            return LockoutResult(locked=True, retry_after_seconds=retry_after)

    def register_login_failure(
        self,
        *,
        key: str,
        threshold: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> LockoutResult:
        now = datetime.now(UTC)
        window = timedelta(seconds=window_seconds)
        locked_until = now + timedelta(seconds=lockout_seconds)
        with self._lock:
            events = self._failed_login_events[key]
            self._prune(events, now=now, window=window)
            events.append(now)
            if len(events) < threshold:
                return LockoutResult(locked=False, retry_after_seconds=0)

            self._lockouts[key] = locked_until
            return LockoutResult(locked=True, retry_after_seconds=lockout_seconds)

    def clear_login_failures(self, *, key: str) -> None:
        with self._lock:
            self._failed_login_events.pop(key, None)
            self._lockouts.pop(key, None)

    @staticmethod
    def _prune(events: deque[datetime], *, now: datetime, window: timedelta) -> None:
        while events and now - events[0] >= window:
            events.popleft()


auth_protection_store = AuthProtectionStore()
