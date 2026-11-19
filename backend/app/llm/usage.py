"""The model-usage ledger — how much of each AI model's free daily allowance is left.

Plain English: the free AI services allow a fixed number of tokens per day (Groq: 200,000 per model, counted
over the last 24 hours). Groq does not publish "tokens left today"; it only states exact numbers when the
limit is hit ("Limit 200000, Used 196840"). So we keep a small logbook (backend/data/usage.sqlite, shared by
the website's server and the accuracy test):
  * every answer's token count, per model, with the time  -> our own running total for the last 24 hours;
  * the provider's exact figures whenever it reports them  -> these win over our count ("exact");
  * which models are resting after hitting their limit, and until when.
The website's "model limits" panel reads this (GET /api/usage), and the fallback notices use it too.
"""

import re
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

WINDOW_S = 24 * 3600
ROLES = ["main", "backup", "last resort"]
_NUMBERS = re.compile(r"Limit\s+(\d+),\s*Used\s+(\d+)", re.IGNORECASE)


def limit_numbers(message: str) -> tuple[int, int] | None:
    """(used, limit) from a provider message such as "Limit 200000, Used 196840" — else None."""
    m = _NUMBERS.search(message)
    return (int(m.group(2)), int(m.group(1))) if m else None


class UsageLedger:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path, self.clock = Path(path), clock
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        if not self._ready:  # created on first use, not when the app starts
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS usage (model TEXT, at REAL, tokens INTEGER);
                    CREATE TABLE IF NOT EXISTS reports (model TEXT, at REAL, used INTEGER, lim INTEGER);
                    CREATE TABLE IF NOT EXISTS rests (model TEXT PRIMARY KEY, until REAL);
                    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v REAL);
                """)
                conn.execute("INSERT OR IGNORE INTO meta VALUES ('created', ?)", (self.clock(),))
                self._ready = True
        return conn

    # ---- writing ---------------------------------------------------------------------------------------
    def record(self, model: str, tokens: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO usage VALUES (?, ?, ?)", (model, self.clock(), int(tokens)))

    def report(self, model: str, used: int, limit: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO reports VALUES (?, ?, ?, ?)", (model, self.clock(), int(used), int(limit)))

    def rest(self, model: str, seconds: float) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO rests VALUES (?, ?)", (model, self.clock() + seconds))

    # ---- reading ---------------------------------------------------------------------------------------
    def resting_until(self, model: str) -> float | None:
        with self._connect() as conn:
            row = conn.execute("SELECT until FROM rests WHERE model = ?", (model,)).fetchone()
        return row[0] if row and row[0] > self.clock() else None

    def snapshot(self, models: list[str], limits: dict[str, int]) -> list[dict]:
        """One row per model, in fallback order: role, status, tokens used / left in the last 24 hours."""
        now = self.clock()
        since = now - WINDOW_S
        rows = []
        with self._connect() as conn:
            created = conn.execute("SELECT v FROM meta WHERE k = 'created'").fetchone()[0]
            for i, model in enumerate(models):
                report = conn.execute("SELECT at, used, lim FROM reports WHERE model = ? AND at > ? "
                                      "ORDER BY at DESC LIMIT 1", (model, since)).fetchone()
                start = report[0] if report else since
                after = conn.execute("SELECT COALESCE(SUM(tokens), 0), COUNT(*) FROM usage WHERE model = ? AND at > ?",
                                     (model, start)).fetchone()
                used = (report[1] if report else 0) + after[0]
                limit = report[2] if report else limits.get(model)
                until = conn.execute("SELECT until FROM rests WHERE model = ?", (model,)).fetchone()
                resting = bool(until and until[0] > now)
                rows.append({
                    "model": model,
                    "role": ROLES[min(i, len(ROLES) - 1)],
                    "status": "resting" if resting else "available",
                    "back_in_s": round(until[0] - now) if resting else None,
                    "daily_limit": limit,
                    "used": used,
                    "remaining": max(0, limit - used) if limit else None,
                    "exact": bool(report) and after[1] == 0,  # the provider's own figure, nothing used since
                    # Our count covers the whole 24 hours only once the logbook is that old (or the provider
                    # gave a figure); before that, earlier use is missing and "remaining" may be too high.
                    "counting_since": created,
                    "complete": bool(report) or created <= since,
                })
        return rows
