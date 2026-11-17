"""LLM client: picks the AI provider from settings and gets reliable text/JSON out of it."""

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.config import Settings
from app.llm.client import LLMConfigError, LLMOutputError, ask_json, ask_text, get_chat_model, make_provider


class Decision(BaseModel):
    kind: str


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_groq_selected_by_default():
    s = _settings(groq_api_key="test-key")
    assert isinstance(make_provider(s, s.llm_provider), ChatGroq)
    get_chat_model(s)  # builds without any network call


def test_missing_key_raises_config_error():
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        get_chat_model(_settings())


def test_ask_text_returns_content():
    llm = FakeListChatModel(responses=["hello"])
    assert ask_text(llm, "system", "user") == "hello"


def test_ask_json_parses_fenced_json():
    llm = FakeListChatModel(responses=['Sure! ```json\n{"kind": "sql"}\n``` hope that helps'])
    assert ask_json(llm, "sys", "user", Decision) == Decision(kind="sql")


def test_ask_json_repairs_once():
    llm = FakeListChatModel(responses=["not json at all", '{"kind": "refuse"}'])
    assert ask_json(llm, "sys", "user", Decision).kind == "refuse"


def test_ask_json_gives_up():
    llm = FakeListChatModel(responses=["nope", "still nope"])
    with pytest.raises(LLMOutputError):
        ask_json(llm, "sys", "user", Decision)
