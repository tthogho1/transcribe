"""Build the chat LLM clients from environment variables."""

import os
from typing import Tuple

from services.llm.base import LLMClient
from services.llm.openai_client import OpenAIChatClient

PROVIDERS = ("openai", "ollama")


def llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def create_llm_clients(openai_client=None) -> Tuple[LLMClient, LLMClient]:
    """(answer_llm, rewrite_llm) for the provider in LLM_PROVIDER.

    answer_llm writes the answers; rewrite_llm runs the small follow-up
    check before each search, so it can be a cheaper model.

    LLM_PROVIDER=openai (default):
      OPENAI_MODEL          answers           (default gpt-3.5-turbo)
      OPENAI_REWRITE_MODEL  follow-up check   (default gpt-4.1-mini)
      OPENAI_API_KEY, OPENAI_BASE_URL         read by the OpenAI SDK

    LLM_PROVIDER=ollama:
      OLLAMA_MODEL          answers           (default qwen2.5:7b)
      OLLAMA_REWRITE_MODEL  follow-up check   (default: OLLAMA_MODEL)
      OLLAMA_BASE_URL       (default http://localhost:11434)
      OLLAMA_NUM_CTX        context window in tokens (default 16384)
      OLLAMA_TIMEOUT        seconds per request (default 300)

    `openai_client` replaces the OpenAI SDK client (tests pass a fake).
    """
    provider = llm_provider()

    if provider == "openai":
        if openai_client is None:
            from openai import OpenAI
            openai_client = OpenAI()
        return (
            OpenAIChatClient(os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"), openai_client),
            OpenAIChatClient(os.getenv("OPENAI_REWRITE_MODEL", "gpt-4.1-mini"), openai_client),
        )

    if provider == "ollama":
        import requests

        from services.llm.ollama_client import OllamaChatClient

        model = os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"
        settings = dict(
            base_url=os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434",
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX") or "16384"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT") or "300"),
            session=requests.Session(),  # shared: one connection pool
        )
        return (
            OllamaChatClient(model, **settings),
            OllamaChatClient(os.getenv("OLLAMA_REWRITE_MODEL") or model, **settings),
        )

    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}: use one of {', '.join(PROVIDERS)}")
