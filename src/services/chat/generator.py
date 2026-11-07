"""Answer a question from search results with an OpenAI chat model."""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from deep_translator import GoogleTranslator
from openai import OpenAI

from models.conversation_chunk import SearchResult
from services.chat.language import detect_language
from services.chat.prompts import ANSWER_SYSTEM_PROMPT, ANSWER_USER_PROMPT

logger = logging.getLogger(__name__)

Message = Dict[str, str]  # {"role": ..., "content": ...}


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


class AnswerGenerator:
    """Answers a question from search results with an OpenAI chat model.

    `client` is an OpenAI client; by default one is created from
    OPENAI_API_KEY. ChatService also uses it for the follow-up check.
    """

    def __init__(self, client: Optional[OpenAI] = None):
        self.client = client or OpenAI()
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    def generate(
        self,
        query: str,
        search_results: List[SearchResult],
        history: List[Message],
        answer_in_english: bool,
    ) -> GeneratedAnswer:
        """Answer `query` from `search_results`, continuing `history`.

        Raises whatever OpenAI or the translation raises, and ValueError if
        the model returns no answer (e.g. a refusal).
        """
        language = "English" if answer_in_english else "Japanese"
        system_prompt = f"{ANSWER_SYSTEM_PROMPT}\n- Answer in {language}"
        user_prompt = ANSWER_USER_PROMPT.format(
            query=query, context=format_context(search_results)
        )
        logger.debug(user_prompt)

        response = self._complete(system_prompt, user_prompt, history)

        # content is None on refusals; never let None reach the session
        # history, where it breaks every later request for this user.
        answer = response.choices[0].message.content or ""
        if not answer.strip():
            raise ValueError("OpenAI returned an empty answer")

        if answer_in_english and detect_language(answer) == "ja":
            logger.info("Translating response back to English...")
            answer = GoogleTranslator(source="ja", target="en").translate(answer)

        return GeneratedAnswer(answer, getattr(response.usage, "total_tokens", 0))

    def _complete(self, system_prompt: str, user_prompt: str, history: List[Message]):
        """Call the model; if the prompt is too long, retry once with less history."""
        try:
            return self._create(system_prompt, user_prompt, trim_history(history))
        except Exception as e:
            if "maximum context length" not in str(e).lower():
                raise
            logger.warning("Token limit exceeded, trimming more aggressively")
            shorter = trim_history(history, max_turns=10, max_tokens=2000)
            return self._create(system_prompt, user_prompt, shorter)

    def _create(self, system_prompt: str, user_prompt: str, history: List[Message]):
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_prompt},
        ]
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
