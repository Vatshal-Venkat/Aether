"""A small answer cache: remember recent answers for a while (LRU + time limit).

Plain English: if someone asks exactly the same first question again within 10 minutes, as the same
person (same role and patient), answer instantly from memory instead of asking the AI again — faster,
and it saves the free AI allowance. The cache holds at most a few hundred answers; when full, the one
used longest ago is dropped. `clock` is injectable so tests can fast-forward time.
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: float = 600, clock: Callable[[], float] = time.monotonic):
        self.maxsize, self.ttl, self.clock = maxsize, ttl, clock
        self._items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            stored_at, value = item
            if self.clock() - stored_at > self.ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)  # recently used
            return value

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._items[key] = (self.clock(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)  # drop the least recently used
