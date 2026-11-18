"""Big result tables, handed out a page at a time.

Plain English: a question like "list all encounters" can return 1,000 rows. Sending them all at once
is slow and heavy, so the answer carries only the first 100 rows plus a ticket (result_id). The website
uses the ticket to fetch the next 100, and so on. Tickets expire after 30 minutes, and a ticket only
works for the person who asked (same role and patient) — anyone else is told it doesn't exist.
"""

import math
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

Owner = tuple[str, str | None]  # (role, patient_id)


class ResultStore:
    def __init__(self, ttl: float = 1800, page_size: int = 100, max_results: int = 200,
                 clock: Callable[[], float] = time.monotonic):
        self.ttl, self.page_size, self.max_results, self.clock = ttl, page_size, max_results, clock
        self._items: dict[str, tuple[float, Owner, list[str], list[list[Any]]]] = {}
        self._lock = threading.Lock()

    def put(self, columns: list[str], rows: list[list[Any]], owner: Owner) -> str:
        rid = uuid.uuid4().hex
        with self._lock:
            now = self.clock()
            for key in [k for k, v in self._items.items() if now - v[0] > self.ttl]:
                del self._items[key]
            while len(self._items) >= self.max_results:  # keep memory bounded: drop the oldest
                del self._items[min(self._items, key=lambda k: self._items[k][0])]
            self._items[rid] = (now, owner, columns, rows)
        return rid

    def page(self, rid: str, page: int, owner: Owner) -> dict | None:
        """Page n (1-based) of a stored result, or None if unknown, expired, or not this person's."""
        with self._lock:
            item = self._items.get(rid)
        if item is None or self.clock() - item[0] > self.ttl or item[1] != owner:
            return None
        _, _, columns, rows = item
        pages = max(1, math.ceil(len(rows) / self.page_size))
        if not 1 <= page <= pages:
            raise ValueError(f"page must be between 1 and {pages}")
        start = (page - 1) * self.page_size
        return {"columns": columns, "rows": rows[start:start + self.page_size], "page": page, "pages": pages,
                "total_rows": len(rows)}
