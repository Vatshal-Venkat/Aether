"""Operations kit: the parts that make Aether behave like a service (Plan 5).

Plain English: the pipeline answers questions; these parts look after HOW it's used — remember recent
answers (cache), hand out big tables in pages, stop floods (rate limit), let only a couple of questions
use the AI at once (queue), keep a logbook (audit) and count everything (metrics). One `Ops` object
holds them all; the API creates it once.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.ops.audit import AuditLog
from app.ops.cache import TTLCache
from app.ops.metrics import Metrics
from app.ops.ratelimit import SlidingWindow
from app.ops.results import ResultStore


@dataclass
class Ops:
    audit: AuditLog
    metrics: Metrics
    cache: TTLCache
    results: ResultStore
    limiter: SlidingWindow
    slots: threading.BoundedSemaphore
    audit_api_enabled: bool = False

    @classmethod
    def from_settings(cls, s: Settings) -> "Ops":
        return cls(
            audit=AuditLog(s.audit_path),
            metrics=Metrics(),
            cache=TTLCache(maxsize=s.cache_size, ttl=s.cache_ttl_s),
            results=ResultStore(ttl=s.results_ttl_s, page_size=s.page_size),
            limiter=SlidingWindow(limit=s.rate_limit, window=s.rate_window_s),
            slots=threading.BoundedSemaphore(s.max_concurrent_chats),
            audit_api_enabled=s.enable_audit_api,
        )

    @classmethod
    def for_tests(cls, tmp_path: Path, **overrides) -> "Ops":
        s = Settings(_env_file=None, audit_path=Path(tmp_path) / "audit.sqlite", **overrides)
        return cls.from_settings(s)
