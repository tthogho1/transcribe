"""
Chat LLM clients behind one small interface (LLMClient).

The chat code calls `llm.chat(messages, ...)` and gets a ChatResult back,
whichever provider is configured. create_llm_clients() picks the provider
from LLM_PROVIDER.
"""

from services.llm.base import ChatResult, ContextTooLongError, LLMClient, LLMError, Message
from services.llm.factory import create_llm_clients

__all__ = [
    "ChatResult", "ContextTooLongError", "LLMClient", "LLMError", "Message", "create_llm_clients",
]
