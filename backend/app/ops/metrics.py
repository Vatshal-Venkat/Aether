"""Live counters, served at GET /metrics in the standard Prometheus text format.

Plain English: a dashboard's raw numbers. How many questions were answered (by kind, and whether from
the cache), how long they took, how long each pipeline step takes, how many SQL tries failed, how often
the cache helped, how often someone was told to slow down, and how many questions are being worked on
right now. Free tools like Prometheus/Grafana can read this page and draw graphs; you can also just
open it in a browser.

Each Metrics object has its own registry, so tests never see each other's numbers.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.graph.runner import ChatResult

BUCKETS = (0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        r = self.registry
        self.requests = Counter("aether_requests", "Questions answered, by kind and cache use", ["kind", "cached"], registry=r)
        self.request_seconds = Histogram("aether_request_seconds", "Time to answer a question", buckets=BUCKETS, registry=r)
        self.step_seconds = Histogram("aether_step_seconds", "Time spent in each pipeline step", ["step"],
                                      buckets=BUCKETS, registry=r)
        self.sql_errors = Counter("aether_sql_errors", "SQL tries that failed (rejected or database error)", registry=r)
        self.cache_lookups = Counter("aether_cache_lookups", "Answer-cache lookups", ["result"], registry=r)
        self.limited = Counter("aether_rate_limited", "Requests refused for asking too fast", registry=r)
        self.in_flight = Gauge("aether_in_flight", "Questions being worked on right now", registry=r)

    def observe(self, result: ChatResult, seconds: float, cached: bool) -> None:
        self.requests.labels(kind=result.kind, cached=str(cached).lower()).inc()
        self.request_seconds.observe(seconds)
        if cached:
            self.cache_lookups.labels(result="hit").inc()
            return  # the steps didn't run again
        for step, t in result.timings.items():
            self.step_seconds.labels(step=step).observe(t)
        self.sql_errors.inc(sum(1 for s in result.sql if s.error))

    def cache_miss(self) -> None:
        self.cache_lookups.labels(result="miss").inc()

    def rate_limited(self) -> None:
        self.limited.inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
