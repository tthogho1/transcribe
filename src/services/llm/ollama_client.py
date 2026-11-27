"""LLMClient for a local Ollama server (native /api/chat)."""

from typing import List, Optional

import requests

from services.llm.base import ChatResult, ContextTooLongError, LLMError, Message


def estimate_tokens(messages: List[Message]) -> int:
    """A deliberately high token estimate: one token per character.

    Close for Japanese (what this app mostly sends) and an overestimate for
    English, so a prompt that passes this check fits in the context window.
    """
    return sum(len(m["content"]) + 4 for m in messages)  # + role/formatting tokens


class OllamaChatClient:
    """Ollama chat with one model.

    Uses Ollama's own API rather than its OpenAI-compatible one so each
    request can set the context window (num_ctx).

    Ollama silently cuts a prompt that doesn't fit in num_ctx, dropping the
    system prompt with it, instead of returning an error. So chat() checks
    the size first and raises ContextTooLongError, like the OpenAI client.
    """

    provider = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        num_ctx: int = 16384,
        timeout: float = 300,
        session: Optional[requests.Session] = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.http = session or requests.Session()

    def chat(
        self,
        messages: List[Message],
        *,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
    ) -> ChatResult:
        needed = estimate_tokens(messages) + max_tokens
        if needed > self.num_ctx:
            raise ContextTooLongError(
                f"Prompt needs about {needed} tokens (incl. {max_tokens} for the answer) "
                f"but OLLAMA_NUM_CTX is {self.num_ctx}"
            )

        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if json_mode:
            body["format"] = "json"

        try:
            response = self.http.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except requests.ConnectionError as e:
            raise LLMError(
                f"Cannot reach Ollama at {self.base_url}: is `ollama serve` running?"
            ) from e

        if response.status_code != 200:
            raise LLMError(f"Ollama returned {response.status_code}: {_error_message(response)}")

        data = response.json()
        return ChatResult(
            text=(data.get("message") or {}).get("content") or "",
            total_tokens=(data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0),
        )


def _error_message(response: requests.Response) -> str:
    try:
        return response.json().get("error") or response.text[:200]
    except ValueError:
        return response.text[:200]
