"""@timed — a stopwatch for each pipeline step, so we can see where time goes."""

import functools
import time


def timed(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state, deps):
            start = time.perf_counter()
            out = fn(state, deps) or {}
            return {**out, "timings": {name: round(time.perf_counter() - start, 4)}}

        return wrapper

    return decorator
