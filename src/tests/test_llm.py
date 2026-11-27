"""Tests for services/llm: the OpenAI client wrapper and the factory."""

from types import SimpleNamespace

import pytest

from services.llm import ChatResult, ContextTooLongError, create_llm_clients
from services.llm.openai_client import OpenAIChatClient

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "質問"}]


class FakeCompletions:
    """Records create() calls and replies with `reply` (or raises it)."""

    def __init__(self, reply="答え", usage=SimpleNamespace(total_tokens=42)):
        self.reply, self.usage, self.calls = reply, usage, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self.usage)


def fake_sdk(**kwargs):
    completions = FakeCompletions(**kwargs)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


# --- OpenAIChatClient -------------------------------------------------------

def test_chat_sends_model_messages_and_settings():
    sdk, completions = fake_sdk()
    result = OpenAIChatClient("gpt-test", sdk).chat(MESSAGES, max_tokens=100, temperature=0.5)

    assert result == ChatResult(text="答え", total_tokens=42)
    assert completions.calls == [
        {"model": "gpt-test", "messages": MESSAGES, "max_tokens": 100, "temperature": 0.5}
    ]


def test_json_mode_asks_for_a_json_object():
    sdk, completions = fake_sdk(reply='{"ok": true}')
    OpenAIChatClient("gpt-test", sdk).chat(MESSAGES, max_tokens=10, temperature=0, json_mode=True)
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("usage", [None, SimpleNamespace(), SimpleNamespace(total_tokens=None)])
def test_missing_usage_counts_as_zero_tokens(usage):
    sdk, _ = fake_sdk(usage=usage)
    assert OpenAIChatClient("m", sdk).chat(MESSAGES, max_tokens=1, temperature=0).total_tokens == 0


def test_none_content_becomes_empty_text():
    sdk, _ = fake_sdk(reply=None)
    assert OpenAIChatClient("m", sdk).chat(MESSAGES, max_tokens=1, temperature=0).text == ""


class FakeBadRequest(Exception):
    """Like openai.BadRequestError: the error code is an attribute."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


@pytest.mark.parametrize("error", [
    FakeBadRequest("Error code: 400", code="context_length_exceeded"),
    RuntimeError("This model's maximum context length is 8192 tokens"),
])
def test_context_length_errors_become_context_too_long(error):
    sdk, _ = fake_sdk(reply=error)
    with pytest.raises(ContextTooLongError):
        OpenAIChatClient("m", sdk).chat(MESSAGES, max_tokens=1, temperature=0)


def test_other_errors_propagate_unchanged():
    error = FakeBadRequest("rate limited", code="rate_limit_exceeded")
    sdk, _ = fake_sdk(reply=error)
    with pytest.raises(FakeBadRequest) as raised:
        OpenAIChatClient("m", sdk).chat(MESSAGES, max_tokens=1, temperature=0)
    assert raised.value is error


# --- factory ----------------------------------------------------------------

@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "OPENAI_MODEL", "OPENAI_REWRITE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_openai_is_the_default_provider(clean_env):
    sdk, _ = fake_sdk()
    answer_llm, rewrite_llm = create_llm_clients(openai_client=sdk)

    assert (answer_llm.provider, answer_llm.model) == ("openai", "gpt-3.5-turbo")
    assert (rewrite_llm.provider, rewrite_llm.model) == ("openai", "gpt-4.1-mini")
    assert answer_llm.client is rewrite_llm.client is sdk  # one SDK client, shared


def test_models_come_from_the_environment(clean_env):
    clean_env.setenv("LLM_PROVIDER", " OpenAI ")
    clean_env.setenv("OPENAI_MODEL", "gpt-4.1")
    clean_env.setenv("OPENAI_REWRITE_MODEL", "gpt-4.1-nano")

    answer_llm, rewrite_llm = create_llm_clients(openai_client=fake_sdk()[0])

    assert (answer_llm.model, rewrite_llm.model) == ("gpt-4.1", "gpt-4.1-nano")


def test_unknown_provider_is_rejected(clean_env):
    clean_env.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError, match="gemini"):
        create_llm_clients(openai_client=fake_sdk()[0])


# --- OllamaChatClient -------------------------------------------------------

import requests  # noqa: E402

from services.llm import LLMError  # noqa: E402
from services.llm.ollama_client import OllamaChatClient, estimate_tokens  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status_code, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload


class FakeSession:
    """Records POSTs to Ollama and returns `response` (or raises it)."""

    def __init__(self, response=None):
        self.response = response or FakeResponse(payload={
            "message": {"role": "assistant", "content": "答え"},
            "prompt_eval_count": 30, "eval_count": 12, "done_reason": "stop",
        })
        self.posts = []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def ollama(session=None, **kwargs):
    return OllamaChatClient("qwen2.5:7b", session=session or FakeSession(), **kwargs)


def test_ollama_sends_model_messages_and_options():
    session = FakeSession()
    client = ollama(session, base_url="http://gpu-box:11434/", num_ctx=8192, timeout=60)

    result = client.chat(MESSAGES, max_tokens=100, temperature=0.5)

    assert result == ChatResult(text="答え", total_tokens=42)  # prompt 30 + answer 12
    (post,) = session.posts
    assert post["url"] == "http://gpu-box:11434/api/chat"
    assert post["timeout"] == 60
    assert post["json"] == {
        "model": "qwen2.5:7b", "messages": MESSAGES, "stream": False,
        "options": {"num_ctx": 8192, "num_predict": 100, "temperature": 0.5},
    }


def test_ollama_json_mode_sets_format():
    session = FakeSession()
    ollama(session).chat(MESSAGES, max_tokens=10, temperature=0, json_mode=True)
    assert session.posts[0]["json"]["format"] == "json"


def test_ollama_prompt_too_long_is_refused_before_sending():
    # Ollama would silently cut the prompt (losing the system prompt), so the
    # client refuses it up front and the generator can retry with less history.
    session = FakeSession()
    long_messages = [{"role": "user", "content": "あ" * 900}]

    with pytest.raises(ContextTooLongError, match="OLLAMA_NUM_CTX is 1000"):
        ollama(session, num_ctx=1000).chat(long_messages, max_tokens=200, temperature=0)
    assert session.posts == []


def test_estimate_counts_one_token_per_character():
    assert estimate_tokens([{"role": "user", "content": "あいう"}]) == 3 + 4


@pytest.mark.parametrize("payload, text, tokens", [
    ({"message": {"content": None}}, "", 0),
    ({"message": {"content": "x"}}, "x", 0),
    ({}, "", 0),
])
def test_ollama_missing_fields_are_safe(payload, text, tokens):
    result = ollama(FakeSession(FakeResponse(payload=payload))).chat(MESSAGES, max_tokens=1, temperature=0)
    assert (result.text, result.total_tokens) == (text, tokens)


def test_ollama_http_error_carries_ollama_message():
    session = FakeSession(FakeResponse(404, payload={"error": "model 'qwen2.5:7b' not found"}))
    with pytest.raises(LLMError, match="404: model 'qwen2.5:7b' not found"):
        ollama(session).chat(MESSAGES, max_tokens=1, temperature=0)


def test_ollama_http_error_without_json_uses_text():
    session = FakeSession(FakeResponse(500, payload=None, text="internal error"))
    with pytest.raises(LLMError, match="500: internal error"):
        ollama(session).chat(MESSAGES, max_tokens=1, temperature=0)


def test_ollama_not_running_says_so():
    session = FakeSession(requests.ConnectionError("refused"))
    with pytest.raises(LLMError, match="is `ollama serve` running"):
        ollama(session).chat(MESSAGES, max_tokens=1, temperature=0)


# --- factory: ollama --------------------------------------------------------

@pytest.fixture
def ollama_env(clean_env):
    for name in ("OLLAMA_MODEL", "OLLAMA_REWRITE_MODEL", "OLLAMA_BASE_URL", "OLLAMA_NUM_CTX", "OLLAMA_TIMEOUT"):
        clean_env.delenv(name, raising=False)
    clean_env.setenv("LLM_PROVIDER", "ollama")
    return clean_env


def test_ollama_defaults(ollama_env):
    answer_llm, rewrite_llm = create_llm_clients()

    assert (answer_llm.provider, answer_llm.model) == ("ollama", "qwen2.5:7b")
    assert rewrite_llm.model == "qwen2.5:7b"  # same model unless OLLAMA_REWRITE_MODEL is set
    assert (answer_llm.base_url, answer_llm.num_ctx, answer_llm.timeout) == ("http://localhost:11434", 16384, 300)
    assert answer_llm.http is rewrite_llm.http


def test_ollama_settings_from_environment(ollama_env):
    ollama_env.setenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_env.setenv("OLLAMA_REWRITE_MODEL", "phi3:mini")
    ollama_env.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434")
    ollama_env.setenv("OLLAMA_NUM_CTX", "32768")
    ollama_env.setenv("OLLAMA_TIMEOUT", "90")

    answer_llm, rewrite_llm = create_llm_clients()

    assert (answer_llm.model, rewrite_llm.model) == ("llama3.1:8b", "phi3:mini")
    assert (answer_llm.base_url, answer_llm.num_ctx, answer_llm.timeout) == ("http://gpu-box:11434", 32768, 90)


def test_ollama_needs_no_openai_key(ollama_env):
    ollama_env.delenv("OPENAI_API_KEY", raising=False)
    create_llm_clients()  # must not try to build an OpenAI client
