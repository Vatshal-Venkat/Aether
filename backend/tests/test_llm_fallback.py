"""Fallback models: when the main Groq model's DAILY allowance is used up, Aether moves straight to the
smaller Groq model (no pointless retries) and leaves the main model alone until Groq says it's back."""

import groq
import httpx
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_groq import ChatGroq

from app.config import Settings
from app.graph.runner import friendly_error, is_rate_limit
from app.llm.client import DailyLimitReached, build_chain, chat_models

DAILY = ("Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000, "
         "Used 199868, Requested 1189. Please try again in 7m36.6s.")
PER_MINUTE = "Rate limit reached for model `openai/gpt-oss-120b` on tokens per minute (TPM). Please try again in 2.1s."


def _rate_limit(message: str) -> groq.RateLimitError:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
    return groq.RateLimitError(message, response=response, body=None)


class Model:
    """A stand-in AI model: replies with its name, or raises the errors it was given first."""

    def __init__(self, name: str, errors=()):
        self.name, self.errors, self.calls = name, list(errors), 0

    def runnable(self):
        def call(messages):
            self.calls += 1
            if self.errors:
                raise self.errors.pop(0)
            return AIMessage(self.name)
        return RunnableLambda(call)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, groq_api_key="test-key", **kw)


def test_fallback_model_is_on_by_default_after_the_main_model():
    names = [m.model_name for m in chat_models(_settings())]
    assert names == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


def test_fallback_model_can_be_switched_off_or_changed():
    assert [m.model_name for m in chat_models(_settings(groq_fallback_model=""))] == ["openai/gpt-oss-120b"]
    assert [m.model_name for m in chat_models(_settings(groq_fallback_model="llama-3.1-8b-instant"))] == [
        "openai/gpt-oss-120b", "llama-3.1-8b-instant"]


def test_fallback_model_same_as_main_is_not_added_twice():
    models = chat_models(_settings(groq_model="openai/gpt-oss-20b"))
    assert [m.model_name for m in models] == ["openai/gpt-oss-20b"]


def test_gemini_comes_after_both_groq_models_when_it_has_a_key():
    models = chat_models(_settings(gemini_api_key="g-key"))
    assert [type(m).__name__ for m in models] == ["ChatGroq", "ChatGroq", "ChatGoogleGenerativeAI"]
    assert isinstance(models[0], ChatGroq)


def test_daily_limit_moves_to_the_fallback_without_retrying():
    main, small = Model("main", [_rate_limit(DAILY)]), Model("small")
    chain = build_chain([main.runnable(), small.runnable()], clock=Clock())
    assert chain.invoke("hi").content == "small"
    assert main.calls == 1  # no retries on a daily limit


def test_main_model_is_skipped_until_groq_says_it_is_back():
    clock = Clock()
    main, small = Model("main", [_rate_limit(DAILY)]), Model("small")
    chain = build_chain([main.runnable(), small.runnable()], clock=clock)
    chain.invoke("first")
    clock.now += 7 * 60  # Groq said 7m36.6s: still resting
    assert chain.invoke("second").content == "small"
    assert main.calls == 1
    clock.now += 40  # now past it: the main model is tried again
    assert chain.invoke("third").content == "main"
    assert main.calls == 2


def test_per_minute_limit_is_still_retried_on_the_same_model():
    main, small = Model("main", [_rate_limit(PER_MINUTE)]), Model("small")
    chain = build_chain([main.runnable(), small.runnable()], clock=Clock())
    assert chain.invoke("hi").content == "main"
    assert main.calls == 2 and small.calls == 0


def test_when_every_model_is_out_the_user_sees_the_rate_limit_message():
    main, small = Model("main", [_rate_limit(DAILY)]), Model("small", [_rate_limit(DAILY.replace("120b", "20b"))])
    chain = build_chain([main.runnable(), small.runnable()], clock=Clock())
    try:
        chain.invoke("hi")
    except DailyLimitReached as exc:
        assert is_rate_limit(exc)
        assert "rate-limited" in friendly_error(exc)
    else:
        raise AssertionError("expected DailyLimitReached")
