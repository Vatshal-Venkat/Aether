"""Small parts: the answer cache, stored result pages, and the rate limiter (each with a fake clock)."""

import pytest

from app.ops.cache import TTLCache
from app.ops.ratelimit import SlidingWindow
from app.ops.results import ResultStore


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_cache_hit_miss_ttl_and_lru():
    clock = Clock()
    cache = TTLCache(maxsize=2, ttl=60, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)                   # "b" was least recently used -> evicted
    assert cache.get("b") is None and cache.get("c") == 3
    clock.now += 61
    assert cache.get("a") is None       # expired


def test_result_pages_and_scoping():
    clock = Clock()
    store = ResultStore(ttl=1800, page_size=100, clock=clock)
    rows = [[i] for i in range(250)]
    rid = store.put(["n"], rows, owner=("patient", "p1"))
    page2 = store.page(rid, 2, owner=("patient", "p1"))
    assert page2["rows"][0] == [100] and len(page2["rows"]) == 100 and page2["pages"] == 3 and page2["total_rows"] == 250
    assert len(store.page(rid, 3, owner=("patient", "p1"))["rows"]) == 50
    assert store.page(rid, 2, owner=("patient", "p2")) is None      # another patient: as if it didn't exist
    assert store.page(rid, 2, owner=("clinician", None)) is None
    with pytest.raises(ValueError):
        store.page(rid, 4, owner=("patient", "p1"))
    clock.now += 1801
    assert store.page(rid, 1, owner=("patient", "p1")) is None      # expired


def test_sliding_window():
    clock = Clock()
    limiter = SlidingWindow(limit=2, window=60, clock=clock)
    assert limiter.allow("ip")[0] and limiter.allow("ip")[0]
    ok, retry_after = limiter.allow("ip")
    assert not ok and 0 < retry_after <= 60
    assert limiter.allow("other-ip")[0]
    clock.now += 61
    assert limiter.allow("ip")[0]
