"""The interface every chat LLM client implements."""

from dataclasses import dataclass
from typing import Dict, List, Protocol

Message = Dict[str, str]  # {"role": "system" | "user" | "assistant", "content": ...}


@dataclass(frozen=True)
class ChatResult:
    text: str  # "" when the model returned nothing (e.g. a refusal)
    total_tokens: int  # prompt + completion, as reported by the provider (0 if unknown)


class LLMError(Exception):
    """The LLM provider failed (unreachable, unknown model, server error...)."""


class ContextTooLongError(LLMError):
    """The prompt doesn't fit in the model's context window."""


class LLMClient(Protocol):
    """A chat model, bound to one provider and one model name."""

    provider: str  # "openai", "ollama", ...
    model: str

    def chat(
        self,
        messages: List[Message],
        *,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
    ) -> ChatResult:
        """One chat completion.

        json_mode asks the model to reply with a single JSON object.
        Raises ContextTooLongError if the prompt is too long for the model;
        other provider errors propagate as they are.
        """
        ...
