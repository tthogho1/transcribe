"""Answer a question from search results with a chat LLM."""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from deep_translator import GoogleTranslator

from models.conversation_chunk import SearchResult
from services.chat.language import detect_language
from services.chat.prompts import ANSWER_SYSTEM_PROMPT, ANSWER_USER_PROMPT
from services.llm import ChatResult, ContextTooLongError, LLMClient, Message, create_llm_clients

logger = logging.getLogger(__name__)


@dataclass
class GeneratedAnswer:
    text: str
    tokens_used: int  # whole call: prompt (incl. context and history) + answer


def trim_history(
    history: List[Message], max_turns: int = 20, max_tokens: int = 4000
) -> List[Message]:
    """The most recent user/assistant messages that fit in `max_turns`
    messages and roughly `max_tokens` tokens (1 token ≈ 4 characters).
    At least the last two messages are always kept."""
    conversation = [m for m in history if m["role"] in ("user", "assistant")]
    conversation = conversation[-max_turns:]

    total_tokens = sum(len(m["content"]) // 4 for m in conversation)
    while total_tokens > max_tokens and len(conversation) > 2:
        removed = conversation.pop(0)
        total_tokens -= len(removed["content"]) // 4
    return conversation


def format_context(search_results: List[SearchResult]) -> str:
    """Search results as numbered context blocks for the answer prompt."""
    return "\n".join(
        f"[Context {i}] Speaker: {r.speaker}\n"
        f"Content: {r.text}\n"
        f"Timestamp: {r.timestamp}\n"
        f"Relevance Score: {r.score:.3f}\n"
        for i, r in enumerate(search_results, 1)
    )


def _setting(name: str, legacy_name: str, default: str) -> str:
    """LLM_* setting, falling back to its older OPENAI_* name."""
    return os.getenv(name) or os.getenv(legacy_name) or default


class AnswerGenerator:
    """Answers a question from search results with a chat LLM.

    `llm` is the answer model; by default it comes from create_llm_clients()
    (LLM_PROVIDER). Length and randomness are set by LLM_MAX_TOKENS and
    LLM_TEMPERATURE (older names: OPENAI_MAX_TOKENS, OPENAI_TEMPERATURE).
    """

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or create_llm_clients()[0]
        self.max_tokens = int(_setting("LLM_MAX_TOKENS", "OPENAI_MAX_TOKENS", "2000"))
        self.temperature = float(_setting("LLM_TEMPERATURE", "OPENAI_TEMPERATURE", "0.7"))

    def generate(
        self,
        query: str,
        search_results: List[SearchResult],
        history: List[Message],
        answer_in_english: bool,
    ) -> GeneratedAnswer:
        """Answer `query` from `search_results`, continuing `history`.

        Raises whatever the LLM or the translation raises, and ValueError if
        the model returns no answer (e.g. a refusal).
        """
        language = "English" if answer_in_english else "Japanese"
        system_prompt = f"{ANSWER_SYSTEM_PROMPT}\n- Answer in {language}"
        user_prompt = ANSWER_USER_PROMPT.format(
            query=query, context=format_context(search_results)
        )
        logger.debug(user_prompt)

        result = self._complete(system_prompt, user_prompt, history)

        # An empty answer (e.g. a refusal) must never reach the session
        # history, where it would break every later request for this user.
        answer = result.text
        if not answer.strip():
            raise ValueError("The model returned an empty answer")

        if answer_in_english and detect_language(answer) == "ja":
            logger.info("Translating response back to English...")
            answer = GoogleTranslator(source="ja", target="en").translate(answer)

        return GeneratedAnswer(answer, result.total_tokens)

    def _complete(self, system_prompt: str, user_prompt: str, history: List[Message]) -> ChatResult:
        """Call the model; if the prompt is too long, retry once with less history."""
        try:
            return self._chat(system_prompt, user_prompt, trim_history(history))
        except ContextTooLongError:
            logger.warning("Token limit exceeded, trimming more aggressively")
            shorter = trim_history(history, max_turns=10, max_tokens=2000)
            return self._chat(system_prompt, user_prompt, shorter)

    def _chat(self, system_prompt: str, user_prompt: str, history: List[Message]) -> ChatResult:
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_prompt},
        ]
        return self.llm.chat(messages, max_tokens=self.max_tokens, temperature=self.temperature)
