"""LLMClient for the OpenAI API."""

from typing import List, Optional

from openai import OpenAI

from services.llm.base import ChatResult, ContextTooLongError, Message


class OpenAIChatClient:
    """OpenAI chat completions with one model.

    `client` is an OpenAI SDK client; by default one is created from
    OPENAI_API_KEY (and OPENAI_BASE_URL, if set).
    """

    provider = "openai"

    def __init__(self, model: str, client: Optional[OpenAI] = None):
        self.model = model
        self.client = client or OpenAI()

    def chat(
        self,
        messages: List[Message],
        *,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
    ) -> ChatResult:
        kwargs = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if _is_context_length_error(e):
                raise ContextTooLongError(str(e)) from e
            raise

        return ChatResult(
            text=response.choices[0].message.content or "",
            total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
        )


def _is_context_length_error(e: Exception) -> bool:
    # openai.BadRequestError carries code "context_length_exceeded"; the
    # message check also covers proxies and older SDKs that only keep the text.
    return (
        getattr(e, "code", None) == "context_length_exceeded"
        or "maximum context length" in str(e).lower()
    )
