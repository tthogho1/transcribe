"""
Flask chat server: RAG answers over past conversations.

A question is answered in five steps (ChatService.process_chat_query):
  1. non-Japanese questions are translated to Japanese (the index language),
  2. a small LLM decides whether it continues the conversation and, if so,
     rewrites it as a standalone search query,
  3. Zilliz hybrid search finds relevant transcript passages,
  4. OpenAI answers from those passages (and the history, for follow-ups),
  5. the exchange is saved to the user's session.

Served over REST (/api/*) and Socket.IO ("chat_message").
"""

import json
import logging
import os
import re
import secrets
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from deep_translator import GoogleTranslator
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from itsdangerous import BadSignature, URLSafeSerializer
from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException
from openai import OpenAI
from werkzeug.exceptions import HTTPException

from core.conversation_vectorizer import ConversationVectorizer
from models.conversation_chunk import SearchResult
from services.session.session_manager import SessionManager

# ---------------------------------------------------------------------------
# Process setup
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# protobuf prints a harmless version-mismatch warning on import.
warnings.filterwarnings(
    "ignore",
    message=".*gencode version.*is.*older than the runtime version.*",
    category=UserWarning,
    module="google.protobuf.runtime_version",
)

# ---------------------------------------------------------------------------
# Settings and prompts
# ---------------------------------------------------------------------------

DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20

# How much recent history the follow-up classifier sees. Only the latest turns
# matter for "is this a continuation?", and capping each message keeps the
# extra LLM call small and fast.
REWRITE_HISTORY_MESSAGES = 4  # = last 2 user/assistant turns
REWRITE_MESSAGE_CHARS = 500

ANSWER_SYSTEM_PROMPT = """\
Answer users' questions from the given user context.

Important:
Speak in the first person as if you experienced the event yourself.
When referring to past conversations, explain it as your own experience,
not as someone else's.
The context is raw speech-to-text transcription with no punctuation or
sentence breaks, and words are sometimes misrecognized (e.g. "ほばれ" or
"おまれ" for "ほまれ"). Read through the run-on text carefully: you may
infer what was actually SAID (fix misrecognized words, split sentences),
and you do not need an exact literal phrase match to treat a passage
as relevant.

Grounding rules (strict):
- Every fact, situation, example, and quoted phrase in your answer must
  come from the context. Do not add situations, examples, feelings,
  motives, or dictionary meanings that the context does not state.
- Do not generalize or embellish. If the context describes specific
  episodes, answer with those specific episodes rather than a general
  summary that goes beyond them.
- Do not invent example lines or dialogue (e.g. "いやいや、〜").
- If the context only partly answers the question, answer that part and
  say plainly that you don't remember / didn't talk about the rest.
- If the context does not answer the question at all, say so.

Speaking style (the answer should sound like you are talking, not writing):
- Answer casually in a natural conversational tone, as spoken sentences only.
  No bullet points, numbered lists, headings, bold text, or "まとめると" style
  summaries.
- Start with the answer itself. Do not restate or paraphrase the question
  first (e.g. no "〜についてだけど、").
- Talk as if you are remembering it now ("〜の時に言ってたな", "〜なんだよね"),
  not as a report about yourself ("〜という話をしたことがある",
  "〜と自分で言っていた").
- When you mention a word that was misrecognized in the transcript, say the
  correct word (e.g. "駅そば", not "液そば"; "ほまれでございます", not
  "おまれでございます"). This only fixes wording; it never permits adding
  content that the context does not contain.
- Keep it short: a few sentences, at most two short paragraphs.
- Do not close with a generalizing wrap-up ("だから主に〜な時に使ってた",
  "〜って感じかな" that sums up beyond the episodes). Stop after the
  specific episodes.
"""

ANSWER_USER_PROMPT = """\
Question: {query}

Context from relevant conversations:
{context}

Please provide a helpful answer based on the above context.
If the context doesn't contain enough information to answer the question, please say so."""

REWRITE_SYSTEM_PROMPT = """\
You decide whether a user's new question continues the previous conversation, and rewrite it as a standalone search query.

Return JSON only, in this exact shape:
{"is_follow_up": true or false, "standalone_query": "..."}

Rules:
- is_follow_up = true only if the new question cannot be fully understood without the conversation (pronouns like "それ", "その動画", "さっきの", "もっと詳しく", or an obvious continuation of the same topic).
- is_follow_up = false if the question is understandable on its own or changes the topic, even if it is in the same broad area.
- If is_follow_up is true, standalone_query must be one self-contained question with pronouns and omitted subjects replaced by the concrete topic from the conversation.
- If is_follow_up is false, standalone_query must be the new question unchanged.
- Write standalone_query in Japanese (the search index is Japanese). Do not answer the question."""

# Shown to the user in place of an answer; (English, Japanese).
GENERATION_ERROR_MESSAGE = (
    "Sorry, an error occurred while generating the response.",
    "申し訳ございませんが、回答の生成中にエラーが発生しました。",
)
PROCESSING_ERROR_MESSAGE = (
    "Sorry, an error occurred during processing.",
    "申し訳ございませんが、処理中にエラーが発生しました。",
)

# ---------------------------------------------------------------------------
# REST session tokens
# ---------------------------------------------------------------------------

# REST session ids are issued and signed by the server, so a client can only
# use (export, clear, or chat with the history of) a session it was given.
_secret_key = os.getenv("FLASK_SECRET_KEY")
if not _secret_key:
    logger.warning(
        "FLASK_SECRET_KEY is not set; using a random key, so REST user_ids "
        "become invalid when the server restarts"
    )
    _secret_key = secrets.token_hex(32)
_user_id_signer = URLSafeSerializer(_secret_key, salt="chat-user-id")


def issue_user_token() -> Tuple[str, str]:
    """Start a new session: returns (token for the client, session id)."""
    session_id = str(uuid.uuid4())
    return _user_id_signer.dumps(session_id), session_id


def verify_user_token(token: object) -> Optional[str]:
    """The session id inside a token this server issued, else None."""
    if not isinstance(token, str) or not token:
        return None
    try:
        session_id = _user_id_signer.loads(token)
    except BadSignature:
        return None
    return session_id if isinstance(session_id, str) else None


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# langdetect is probabilistic; seed it so the same text always gets the same answer.
DetectorFactory.seed = 0

# Hiragana, katakana (incl. half-width) and CJK ideographs.
_JAPANESE_SCRIPT_RE = re.compile(r"[぀-ヿㇰ-ㇿ㐀-䶿一-鿿ｦ-ﾟ]")


def detect_language(text: str) -> str:
    """A langdetect code for `text`, or "unknown" if it can't tell
    (empty text, or only digits/punctuation/emoji)."""
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def is_japanese_query(text: str) -> bool:
    """True if the user's query should be handled as Japanese.

    Any kana or kanji counts as Japanese: langdetect often labels short
    kanji-only queries (e.g. "東京駅") as Chinese or Korean. Text it can't
    classify (e.g. "2024") also defaults to Japanese, the index's language.
    """
    if _JAPANESE_SCRIPT_RE.search(text):
        return True
    return detect_language(text) in ("ja", "unknown")


# ---------------------------------------------------------------------------
# Answer generation (OpenAI)
# ---------------------------------------------------------------------------

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
    """Answers a question from search results with an OpenAI chat model."""

    def __init__(self):
        self.client = OpenAI()  # reads OPENAI_API_KEY
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


# ---------------------------------------------------------------------------
# Chat pipeline
# ---------------------------------------------------------------------------


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
    """Translation, follow-up detection, search and answer generation."""

    def __init__(self):
        self.vectorizer = ConversationVectorizer(
            os.getenv("ZILLIZ_URI"), os.getenv("ZILLIZ_TOKEN")
        )
        self.generator = AnswerGenerator()
        # Small, fast model for the follow-up check / query rewrite that runs
        # before every search; the answer itself uses OPENAI_MODEL.
        self.rewrite_model = os.getenv("OPENAI_REWRITE_MODEL", "gpt-4.1-mini")
        self.translator = GoogleTranslator(source="auto", target="ja")

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


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.json.ensure_ascii = False  # keep Japanese readable in JSON responses
CORS(app)
# threading mode: eventlet/gevent don't support Python 3.13+
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Connects to Zilliz and loads the embedding model.
chat_service = ChatService()
session_manager = SessionManager()


def run_chat_turn(session_id: str, query: str) -> ChatResponse:
    """Answer `query` in `session_id`'s conversation and save the exchange.

    Error replies are not saved: they would become "context" for the next turn.
    """
    history = session_manager.get_history_for_openai(session_id)
    response = chat_service.process_chat_query(query, history)
    if not response.error:
        # Count each message's own size. response.tokens_used covers the whole
        # call (incl. RAG context); storing it makes the session trimmer drop
        # all but the last exchange.
        session_manager.add_message(session_id, "user", query, tokens=len(query) // 4)
        session_manager.add_message(
            session_id, "assistant", response.answer, tokens=len(response.answer) // 4
        )
    return response


def source_to_dict(result: SearchResult) -> Dict:
    return {
        "text": result.text,
        "speaker": result.speaker,
        "timestamp": result.timestamp,
        "score": result.score,
        "file_name": result.file_name,
    }


def chat_response_to_dict(response: ChatResponse) -> Dict:
    return {
        "answer": response.answer,
        "sources": [source_to_dict(s) for s in response.sources],
        "query": response.query,
        "timestamp": response.timestamp,
        "tokens_used": response.tokens_used,
        "file_names": response.file_names,
        "related_videos": response.related_videos,
    }


# --- REST errors -------------------------------------------------------------


class ApiError(Exception):
    """A client error, returned as {"error": message} with `status`."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@app.errorhandler(ApiError)
def handle_api_error(e: ApiError):
    return jsonify({"error": e.message}), e.status


@app.errorhandler(Exception)
def handle_unexpected_error(e: Exception):
    if isinstance(e, HTTPException):  # 404, 405, ...: keep Flask's response
        return e
    # Details go to the log only; they can reveal internals (hosts, keys, SQL).
    logger.exception(f"Unhandled error on {request.path}")
    return jsonify({"error": "Internal server error"}), 500


def json_body() -> Dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return data


def required_query(data: Dict) -> str:
    query = data.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ApiError(400, "Query is required")
    return query.strip()


def verified_session_id(data: Dict) -> str:
    token = data.get("user_id")
    if not token:
        raise ApiError(400, "user_id is required")
    session_id = verify_user_token(token)
    if session_id is None:
        raise ApiError(403, "invalid user_id")
    return session_id


# --- REST routes -------------------------------------------------------------


@app.get("/")
def index():
    return render_template("chat.html")


@app.post("/api/chat")
def api_chat():
    """Chat with session memory. Send back the returned user_id to continue
    the session; a missing, made-up or tampered one starts a new session."""
    data = json_body()
    query = required_query(data)

    user_token = data.get("user_id")
    session_id = verify_user_token(user_token)
    if session_id is None:
        user_token, session_id = issue_user_token()

    logger.info(f"API /api/chat received query from {session_id}: {query}")
    response = run_chat_turn(session_id, query)
    return jsonify({**chat_response_to_dict(response), "user_id": user_token})


@app.post("/api/search")
def api_search():
    """Search only, no answer generation."""
    data = json_body()
    query = required_query(data)
    limit = data.get("limit", DEFAULT_SEARCH_LIMIT)
    # bool is an int subclass; reject it along with strings/floats.
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ApiError(400, f"limit must be an integer from 1 to {MAX_SEARCH_LIMIT}")

    logger.info(f"API /api/search received query: {query} (limit={limit})")
    results = chat_service.search(query, limit)
    return jsonify({
        "query": query,
        "results": [source_to_dict(r) for r in results],
        "timestamp": datetime.now().isoformat(),
    })


@app.post("/api/session/clear")
def api_clear_session():
    session_manager.clear_session(verified_session_id(json_body()))
    return jsonify({"status": "success", "message": "Session cleared"})


@app.post("/api/session/export")
def api_export_session():
    data = json_body()
    session = session_manager.get_session(verified_session_id(data))
    if not session:
        raise ApiError(404, "No session found")

    return jsonify({
        "user_id": data["user_id"],
        "created_at": session.created_at,
        "last_accessed": session.last_accessed,
        "total_tokens": session.total_tokens,
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp, "tokens": m.tokens}
            for m in session.messages
        ],
    })


@app.get("/api/session/stats")
def api_session_stats():
    return jsonify(session_manager.get_stats())


@app.get("/health")
def health_check():
    session_stats = session_manager.get_stats()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "zilliz": "connected" if chat_service.is_search_connected else "disconnected",
            "openai": "configured" if os.getenv("OPENAI_API_KEY") else "not configured",
            "session_storage": session_stats.get("storage_type", "unknown"),
            "active_sessions": session_stats.get("active_sessions", 0),
        },
    })


# --- Socket.IO ---------------------------------------------------------------


@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("status", {"message": "Connected to chat server"})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("chat_message")
def handle_chat_message(data):
    """Chat with session memory; the socket connection is the session."""
    query = data.get("query") if isinstance(data, dict) else None
    if not isinstance(query, str) or not query.strip():
        emit("chat_error", {"error": "Query is required"})
        return
    query = query.strip()

    session_id = request.sid
    logger.info(f"Processing chat query from {session_id}: {query}")
    try:
        response = run_chat_turn(session_id, query)
    except Exception:
        logger.exception("WebSocket chat error")
        emit("chat_error", {"error": "Internal server error"})
        return
    emit("chat_response", chat_response_to_dict(response))


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 7860))  # 7860: Hugging Face Spaces
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    logger.info(f"Starting Flask chat server on port {port} (debug={debug})")

    # Served directly by Flask-SocketIO's built-in Werkzeug server (no
    # separate WSGI/ASGI server in front of it), so allow_unsafe_werkzeug must
    # stay True even outside debug mode, or socketio.run() refuses to start.
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True)
