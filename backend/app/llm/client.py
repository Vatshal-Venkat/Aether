"""The one doorway to the AI.

Plain English: every time Aether needs the AI (to route a question, write SQL, or phrase
an answer) it goes through this file. That gives us three things in one place:
  * Switching providers is one setting (LLM_PROVIDER=groq|gemini|ollama in .env).
  * Free tiers sometimes say "too many requests" (HTTP 429). We wait a little and retry
    (up to 4 tries, waiting longer each time), then fall back to another configured provider.
  * ask_json() makes the AI's reply machine-readable: we ask for JSON, pull it out even if
    the AI chats around it, check it against a schema, and give the AI one chance to fix it.
"""

import json
import re
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ValidationError

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(Exception):
    """The selected provider can't be used (usually a missing API key)."""


class LLMOutputError(Exception):
    """The AI did not return usable output even after a repair attempt."""


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


def make_provider(settings: Settings, provider: str) -> BaseChatModel:
    """Build one provider's chat model. Raises LLMConfigError if its key is missing."""
    if provider == "groq":
        if not settings.groq_api_key:
            raise LLMConfigError("Set GROQ_API_KEY in backend/.env (free key: https://console.groq.com).")
        from langchain_groq import ChatGroq

        return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0, max_retries=0)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMConfigError("Set GEMINI_API_KEY in backend/.env (free key: https://aistudio.google.com).")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.gemini_model, google_api_key=settings.gemini_api_key, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    raise LLMConfigError(f"Unknown LLM_PROVIDER {provider!r}")


def get_chat_model(settings: Settings) -> Runnable:
    """Selected provider with retry; other providers that have keys become fallbacks."""
    retry = dict(retry_if_exception_type=_transient_errors(), stop_after_attempt=4, wait_exponential_jitter=True)
    primary = make_provider(settings, settings.llm_provider).with_retry(**retry)
    fallbacks = []
    for name in ("groq", "gemini"):  # Ollama is only used when chosen explicitly (it may not be installed)
        if name != settings.llm_provider:
            try:
                fallbacks.append(make_provider(settings, name).with_retry(**retry))
            except LLMConfigError:
                pass
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


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
