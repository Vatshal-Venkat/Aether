"""The model-usage ledger: tokens each AI model used in the last 24 hours, the provider's exact figures when it
reports them, and which models are resting after hitting their daily limit."""

from app.llm.usage import UsageLedger, limit_numbers

DAY = 24 * 3600
MAIN, BACKUP, GEMINI = "openai/gpt-oss-120b", "openai/gpt-oss-20b", "gemini-2.5-flash"
LIMITS = {MAIN: 200_000, BACKUP: 200_000}


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def _ledger(tmp_path, clock):
    return UsageLedger(tmp_path / "usage.sqlite", clock=clock)


def _row(snapshot, model):
    return next(r for r in snapshot if r["model"] == model)


def test_counts_tokens_of_the_last_24_hours(tmp_path):
    clock = Clock()
    ledger = _ledger(tmp_path, clock)
    ledger.record(MAIN, 50_000)
    clock.now += 2 * 3600
    ledger.record(MAIN, 30_000)
    row = _row(ledger.snapshot([MAIN], LIMITS), MAIN)
    assert row["used"] == 80_000 and row["remaining"] == 120_000 and row["exact"] is False
    clock.now += DAY - 3600  # the first 50,000 are now older than 24 hours: freed again
    assert _row(ledger.snapshot([MAIN], LIMITS), MAIN)["used"] == 30_000


def test_a_new_logbook_says_since_when_it_has_been_counting(tmp_path):
    # Usage from before the logbook existed is invisible: until it has covered 24 hours, say so.
    clock = Clock()
    ledger = _ledger(tmp_path, clock)
    started = clock.now
    ledger.record(MAIN, 1_000)
    row = _row(ledger.snapshot([MAIN], LIMITS), MAIN)
    assert row["counting_since"] == started and row["complete"] is False
    clock.now += DAY + 1
    assert _row(ledger.snapshot([MAIN], LIMITS), MAIN)["complete"] is True


def test_the_providers_own_numbers_win(tmp_path):
    clock = Clock()
    ledger = _ledger(tmp_path, clock)
    ledger.record(MAIN, 10_000)                      # our count is lower than reality (e.g. another app used it)
    ledger.report(MAIN, used=196_840, limit=200_000)  # Groq: "Limit 200000, Used 196840"
    row = _row(ledger.snapshot([MAIN], LIMITS), MAIN)
    assert row["used"] == 196_840 and row["remaining"] == 3_160 and row["exact"] is True
    clock.now += 60
    ledger.record(MAIN, 1_000)                       # after the report: Groq's number + what we used since
    row = _row(ledger.snapshot([MAIN], LIMITS), MAIN)
    assert row["remaining"] == 2_160 and row["exact"] is False


def test_resting_models_and_when_they_are_back(tmp_path):
    clock = Clock()
    ledger = _ledger(tmp_path, clock)
    ledger.rest(BACKUP, seconds=708)
    row = _row(ledger.snapshot([MAIN, BACKUP], LIMITS), BACKUP)
    assert row["status"] == "resting" and row["back_in_s"] == 708
    assert ledger.resting_until(BACKUP) == clock.now + 708
    clock.now += 709
    assert _row(ledger.snapshot([MAIN, BACKUP], LIMITS), BACKUP)["status"] == "available"


def test_roles_follow_the_fallback_order_and_unknown_limits_are_allowed(tmp_path):
    ledger = _ledger(tmp_path, Clock())
    ledger.record(GEMINI, 1_234)
    snap = ledger.snapshot([MAIN, BACKUP, GEMINI], LIMITS)
    assert [r["role"] for r in snap] == ["main", "backup", "last resort"]
    gemini = _row(snap, GEMINI)
    assert gemini["daily_limit"] is None and gemini["remaining"] is None and gemini["used"] == 1_234


def test_shared_between_processes_through_the_file(tmp_path):
    clock = Clock()
    _ledger(tmp_path, clock).rest(MAIN, seconds=600)      # e.g. the accuracy test hit the limit
    assert _ledger(tmp_path, clock).resting_until(MAIN) == clock.now + 600  # the website's server knows


def test_limit_numbers_from_a_groq_message():
    msg = ("Rate limit reached for model `openai/gpt-oss-120b` ... on tokens per day (TPD): Limit 200000, "
           "Used 196840, Requested 4799. Please try again in 11m48.04s.")
    assert limit_numbers(msg) == (196_840, 200_000)
    assert limit_numbers("quota exceeded") is None
