"""The one doorway to the AI.

Plain English: every time Aether needs the AI (to route a question, write SQL, or phrase
an answer) it goes through this file. That gives us three things in one place:
  * Switching providers is one setting (LLM_PROVIDER=groq|gemini|ollama in .env).
  * Free tiers sometimes say "too many requests" (HTTP 429). For a short (per-minute) limit we wait a
    little and retry (up to 4 tries, waiting longer each time).
  * When a model's DAILY allowance is used up, retrying is pointless: we move straight to the next model
    and leave the tired one alone until the time the provider says it's back. The order is:
    main Groq model -> smaller Groq model (GROQ_FALLBACK_MODEL, its own allowance) -> Gemini (if keyed).
  * ask_json() makes the AI's reply machine-readable: we ask for JSON, pull it out even if
    the AI chats around it, check it against a schema, and give the AI one chance to fix it.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

from app.config import Settings
from app.llm.usage import UsageLedger, limit_numbers

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(Exception):
    """The selected provider can't be used (usually a missing API key)."""


class LLMOutputError(Exception):
    """The AI did not return usable output even after a repair attempt."""


class DailyLimitReached(Exception):
    """A model's daily allowance is used up (or it is resting until it comes back). Not retried — the next
    model is tried instead. status_code 429 so it is still reported to the user as a rate limit."""

    status_code = 429


_DAILY = re.compile(r"per day|\(TPD\)|\(RPD\)", re.IGNORECASE)
_WAIT = re.compile(r"try again in\s*(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?", re.IGNORECASE)
DEFAULT_REST_S, MAX_REST_S = 300.0, 3600.0


def daily_limit_rest(exc: BaseException) -> float | None:
    """If exc says a DAILY allowance is used up: how many seconds until it's back (else None)."""
    rate_limited = "ratelimit" in type(exc).__name__.lower() or getattr(exc, "status_code", None) == 429
    message = str(exc)
    if not rate_limited or not _DAILY.search(message):
        return None
    m = _WAIT.search(message)
    if not m or not any(m.groups()):
        return DEFAULT_REST_S
    h, mins, secs = (float(g) if g else 0.0 for g in m.groups())
    return min(h * 3600 + mins * 60 + secs, MAX_REST_S)


MODELS_USED_KEY = "aether_models_used"
_models_used: ContextVar[list[str] | None] = ContextVar(MODELS_USED_KEY, default=None)


@contextmanager
def track_models():
    """Collect the name of every model that answered inside this block (one entry per AI call)."""
    used: list[str] = []
    token = _models_used.set(used)
    try:
        yield used
    finally:
        _models_used.reset(token)


def _tokens(reply) -> int:
    usage = getattr(reply, "usage_metadata", None) or {}
    if usage.get("total_tokens"):
        return int(usage["total_tokens"])
    meta = (getattr(reply, "response_metadata", None) or {}).get("token_usage") or {}
    return int(meta.get("total_tokens") or 0)


def _resting(model: Runnable, name: str, clock: Callable[[], float], ledger: "UsageLedger | None" = None) -> Runnable:
    """Wrap a model so a daily-limit error becomes DailyLimitReached and the model rests until it's back.
    With a ledger, tokens and limits are written down (and a rest set by another process is respected)."""
    state = {"until": 0.0}

    def call(messages, config):
        if clock() < state["until"] or (ledger and ledger.resting_until(name)):
            raise DailyLimitReached(f"{name} is resting (daily allowance used up)")
        try:
            reply = model.invoke(messages, config)
        except Exception as exc:
            rest = daily_limit_rest(exc)
            if rest is None:
                raise
            state["until"] = clock() + rest
            if ledger:
                ledger.rest(name, rest)
                if numbers := limit_numbers(str(exc)):
                    ledger.report(name, *numbers)
            log.warning("%s: daily allowance used up; using the next model for %.0f s", name, rest)
            raise DailyLimitReached(str(exc)) from exc
        # Who answered: the pipeline passes a list in its run settings (works across threads, e.g. streaming);
        # track_models() covers direct calls.
        sink = ((config or {}).get("configurable") or {}).get(MODELS_USED_KEY)
        if sink is None:
            sink = _models_used.get()
        if sink is not None:
            sink.append(name)
        if ledger and (tokens := _tokens(reply)):
            try:
                ledger.record(name, tokens)
            except Exception:  # noqa: BLE001 — bookkeeping must never cost the user an answer
                log.warning("could not record token usage for %s", name, exc_info=True)
        return reply

    return RunnableLambda(call, name=f"resting:{name}")


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Errors worth retrying: rate limits, timeouts, dropped connections, server hiccups."""
    import httpx

    errors: list[type[BaseException]] = [httpx.TransportError, TimeoutError, ConnectionError]
    try:
        import groq

        errors += [groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError]
    except ImportError:
        pass
    try:
        from google.genai import errors as genai_errors

        errors += [genai_errors.ServerError, genai_errors.ClientError]  # ClientError includes 429
    except ImportError:
        pass
    return tuple(errors)


def make_provider(settings: Settings, provider: str, model: str | None = None) -> BaseChatModel:
    """Build one provider's chat model. Raises LLMConfigError if its key is missing."""
    if provider == "groq":
        if not settings.groq_api_key:
            raise LLMConfigError("Set GROQ_API_KEY in backend/.env (free key: https://console.groq.com).")
        from langchain_groq import ChatGroq

        return ChatGroq(model=model or settings.groq_model, api_key=settings.groq_api_key, temperature=0, max_retries=0)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMConfigError("Set GEMINI_API_KEY in backend/.env (free key: https://aistudio.google.com).")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.gemini_model, google_api_key=settings.gemini_api_key, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    raise LLMConfigError(f"Unknown LLM_PROVIDER {provider!r}")


def _provider_models(settings: Settings, provider: str) -> list[BaseChatModel]:
    """One provider's models in order. Groq: the main model, then the smaller fallback model."""
    models = [make_provider(settings, provider)]
    fallback = settings.groq_fallback_model.strip()
    if provider == "groq" and fallback and fallback != settings.groq_model:
        models.append(make_provider(settings, "groq", fallback))
    return models


def chat_models(settings: Settings) -> list[BaseChatModel]:
    """Every model to try, in order: the selected provider first, then the others that have keys."""
    models = _provider_models(settings, settings.llm_provider)
    for name in ("groq", "gemini"):  # Ollama is only used when chosen explicitly (it may not be installed)
        if name != settings.llm_provider:
            try:
                models += _provider_models(settings, name)
            except LLMConfigError:
                pass
    return models


def model_name(model) -> str:
    name = getattr(model, "model_name", None) or getattr(model, "model", None) or getattr(model, "name", None)
    return str(name or "model").removeprefix("models/")


def build_chain(models: list[Runnable], clock: Callable[[], float] = time.monotonic,
                ledger: "UsageLedger | None" = None) -> Runnable:
    """Each model retries short limits; a daily limit skips to the next model (which may be resting too)."""
    retry = dict(retry_if_exception_type=_transient_errors(), stop_after_attempt=4, wait_exponential_jitter=True)
    chain = [_resting(m, model_name(m), clock, ledger).with_retry(**retry) for m in models]
    return chain[0].with_fallbacks(chain[1:]) if len(chain) > 1 else chain[0]


def usage_ledger(settings: Settings) -> UsageLedger:
    return UsageLedger(settings.usage_path)


def get_chat_model(settings: Settings, ledger: UsageLedger | None = None) -> Runnable:
    """The selected provider's models, then every other provider that has a key, as fallbacks."""
    return build_chain(chat_models(settings), ledger=ledger)


def _content(message) -> str:
    content = message.content
    if isinstance(content, list):  # some providers return a list of content parts
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content).strip()


def ask_text(llm: Runnable, system: str, user: str) -> str:
    return _content(llm.invoke([SystemMessage(system), HumanMessage(user)]))


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    return text[start : end + 1]


def ask_json(llm: Runnable, system: str, user: str, schema: type[T]) -> T:
    instructions = (
        f"{system}\n\nReply with ONLY a JSON object matching this JSON schema:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    reply = ask_text(llm, instructions, user)
    try:
        return schema.model_validate_json(_extract_json(reply))
    except (ValueError, ValidationError) as first_error:
        repair = f"{user}\n\nYour previous reply was not valid ({str(first_error)[:300]}). Reply with ONLY the JSON object."
        reply = ask_text(llm, instructions, repair)
        try:
            return schema.model_validate_json(_extract_json(reply))
        except (ValueError, ValidationError) as exc:
            raise LLMOutputError(f"AI reply was not valid {schema.__name__} JSON: {exc}") from exc
