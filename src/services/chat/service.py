"""
ChatService: answer a question over past conversations.

  1. non-Japanese questions are translated to Japanese (the index language),
  2. a small LLM decides whether it continues the conversation and, if so,
     rewrites it as a standalone search query,
  3. Zilliz hybrid search finds relevant transcript passages,
  4. OpenAI answers from those passages (and the history, for follow-ups).

Saving the exchange to the session is the caller's job (api.chat_server).
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from deep_translator import GoogleTranslator

from core.conversation_vectorizer import ConversationVectorizer
from models.conversation_chunk import SearchResult
from services.chat.generator import AnswerGenerator, Message
from services.chat.language import is_japanese_query
from services.chat.prompts import REWRITE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 5

# How much recent history the follow-up classifier sees. Only the latest turns
# matter for "is this a continuation?", and capping each message keeps the
# extra LLM call small and fast.
REWRITE_HISTORY_MESSAGES = 4  # = last 2 user/assistant turns
REWRITE_MESSAGE_CHARS = 500

# Shown to the user in place of an answer; (English, Japanese).
GENERATION_ERROR_MESSAGE = (
    "Sorry, an error occurred while generating the response.",
    "申し訳ございませんが、回答の生成中にエラーが発生しました。",
)
PROCESSING_ERROR_MESSAGE = (
    "Sorry, an error occurred during processing.",
    "申し訳ございませんが、処理中にエラーが発生しました。",
)


@dataclass
class QueryAnalysis:
    is_follow_up: bool
    search_query: str


@dataclass
class ChatResponse:
    answer: str
    sources: List[SearchResult]
    query: str  # the user's original question
    timestamp: str
    tokens_used: int
    file_names: List[str]
    related_videos: List[Dict[str, str]] = field(default_factory=list)
    # True when `answer` is an error message; such turns are not saved to history.
    error: bool = False


class ChatService:
    """Translation, follow-up detection, search and answer generation.

    Each component can be passed in (tests do); by default the real ones are
    built from environment variables, which connects to Zilliz and loads the
    embedding model.
    """

    def __init__(
        self,
        vectorizer: Optional[ConversationVectorizer] = None,
        generator: Optional[AnswerGenerator] = None,
        translator: Optional[GoogleTranslator] = None,
    ):
        self.vectorizer = vectorizer or ConversationVectorizer(
            os.getenv("ZILLIZ_URI"), os.getenv("ZILLIZ_TOKEN")
        )
        self.generator = generator or AnswerGenerator()
        # Small, fast model for the follow-up check / query rewrite that runs
        # before every search; the answer itself uses OPENAI_MODEL.
        self.rewrite_model = os.getenv("OPENAI_REWRITE_MODEL", "gpt-4.1-mini")
        self.translator = translator or GoogleTranslator(source="auto", target="ja")

    @property
    def is_search_connected(self) -> bool:
        client = self.vectorizer.bm25_client
        return bool(client and client.collection)

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> List[SearchResult]:
        """Relevant passages: hybrid search, best chunk per video, optional
        reranking, each hit widened with its neighbouring chunks."""
        return self.vectorizer.search_passages(query, limit=limit)

    def process_chat_query(
        self,
        query: str,
        history: Optional[List[Message]] = None,
        max_results: int = DEFAULT_SEARCH_LIMIT,
    ) -> ChatResponse:
        """Answer `query`, continuing `history` if it is a follow-up.

        Never raises: a failure becomes an error-message answer with
        `error=True`, which callers don't save to the session.
        """
        history = history or []
        answer_in_english = not is_japanese_query(query)

        try:
            query_ja = self.translator.translate(query) if answer_in_english else query
            if answer_in_english:
                logger.info(f"Translated prompt for search: {query_ja}")

            # Follow-ups are searched with an LLM-rewritten standalone query and
            # answered with the history; a new topic is searched as-is and
            # answered without it, so an old topic can't leak into the answer.
            analysis = self.analyze_query(query_ja, history)
            search_results = self.search(analysis.search_query, limit=max_results)
        except Exception:
            logger.exception("Error processing chat query")
            return self._error_response(query, answer_in_english, PROCESSING_ERROR_MESSAGE)

        try:
            answer = self.generator.generate(
                query_ja,
                search_results,
                history if analysis.is_follow_up else [],
                answer_in_english,
            )
        except Exception:
            logger.exception("Error generating OpenAI response")
            return self._error_response(
                query, answer_in_english, GENERATION_ERROR_MESSAGE, search_results
            )

        return self._response(query, answer.text, answer.tokens_used, search_results)

    def analyze_query(self, query: str, history: List[Message]) -> QueryAnalysis:
        """Ask a small LLM whether `query` continues the conversation and, if
        so, rewrite it into a self-contained search query.

        With no history there is nothing to continue, so the LLM isn't called.
        If the call fails or returns malformed JSON, the original query is
        searched and the history is still used for the answer, so a
        classifier outage never breaks chat.
        """
        conversation = [m for m in history if m.get("role") in ("user", "assistant")]
        if not conversation:
            return QueryAnalysis(is_follow_up=False, search_query=query)

        history_text = "\n".join(
            f"{m['role']}: {m['content'][:REWRITE_MESSAGE_CHARS]}"
            for m in conversation[-REWRITE_HISTORY_MESSAGES:]
        )
        try:
            response = self.generator.client.chat.completions.create(
                model=self.rewrite_model,
                messages=[
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Conversation:\n{history_text}\n\nNew question: {query}"},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=200,
            )
            result = json.loads(response.choices[0].message.content)
            is_follow_up = result.get("is_follow_up")
            standalone = result.get("standalone_query")
            if not isinstance(is_follow_up, bool):
                raise ValueError(f"is_follow_up is not a bool: {is_follow_up!r}")
        except Exception as e:
            logger.warning(f"Follow-up analysis failed, using original query: {e}")
            return QueryAnalysis(is_follow_up=True, search_query=query)

        if not isinstance(standalone, str) or not standalone.strip():
            standalone = query  # the model left it out: search the question as asked
        search_query = standalone.strip() if is_follow_up else query
        logger.info(f"Follow-up analysis: is_follow_up={is_follow_up}, search_query={search_query!r}")
        return QueryAnalysis(is_follow_up=is_follow_up, search_query=search_query)

    @staticmethod
    def get_related_videos(search_results: List[SearchResult]) -> List[Dict[str, str]]:
        """One {video_id, title, url} per video, in result order. The title
        falls back to the video id for chunks ingested before titles existed."""
        videos: Dict[str, Dict[str, str]] = {}
        for result in search_results:
            video_id = re.sub(r"(_transcription)?\.json$", "", result.file_name)
            videos.setdefault(video_id, {
                "video_id": video_id,
                "title": result.title or video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
        return list(videos.values())

    def _response(
        self, query: str, answer: str, tokens_used: int,
        search_results: List[SearchResult], error: bool = False,
    ) -> ChatResponse:
        return ChatResponse(
            answer=answer,
            sources=search_results,
            query=query,
            timestamp=datetime.now().isoformat(),
            tokens_used=tokens_used,
            file_names=list({r.file_name for r in search_results}),
            related_videos=self.get_related_videos(search_results),
            error=error,
        )

    def _error_response(
        self, query: str, answer_in_english: bool, message: Tuple[str, str],
        search_results: Optional[List[SearchResult]] = None,
    ) -> ChatResponse:
        english, japanese = message
        return self._response(
            query, english if answer_in_english else japanese, 0,
            search_results or [], error=True,
        )
