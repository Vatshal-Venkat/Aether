"""Rate limiting: no one may send more than N questions per minute.

Plain English: each address (IP) may ask, say, 20 questions in any 60-second window. Beyond that the
API answers "Too many questions at once — please wait a moment" (HTTP 429) and says how many seconds
to wait. This protects the free AI allowance and the databases from a flood (or a stuck script).
"""

import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindow:
    def __init__(self, limit: int = 20, window: float = 60, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """(allowed?, seconds to wait if not)."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, round(self.window - (now - hits[0]), 1)
            hits.append(now)
            return True, 0.0
