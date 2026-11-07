"""
Flask Chat Server with Zilliz Cloud and OpenAI Integration
Provides RAG (Retrieval-Augmented Generation) functionality for conversation search
"""

import os
import json
import logging
import re
import secrets
import uuid
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, field

from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from openai import OpenAI
from dotenv import load_dotenv
from itsdangerous import BadSignature, URLSafeSerializer
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from deep_translator import GoogleTranslator

# Import from our models
from models.conversation_chunk import SearchResult
from core.conversation_vectorizer import ConversationVectorizer
from services.session.session_manager import SessionManager

# Load environment variables
load_dotenv()

# Suppress protobuf compatibility warnings
import warnings

warnings.filterwarnings(
    "ignore",
    message=".*gencode version.*is.*older than the runtime version.*",
    category=UserWarning,
    module="google.protobuf.runtime_version",
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)
# Use threading mode to avoid eventlet/gevent on Python 3.13
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# OpenAI client will be initialized in the generator using environment variables

# REST session IDs are issued and signed by the server, so a client can only
# use (export, clear, or chat with the history of) an ID it was given.
_secret_key = os.getenv("FLASK_SECRET_KEY")
if not _secret_key:
    logger.warning(
        "FLASK_SECRET_KEY is not set; using a random key, so REST user_ids "
        "become invalid when the server restarts"
    )
    _secret_key = secrets.token_hex(32)
_user_id_signer = URLSafeSerializer(_secret_key, salt="chat-user-id")


def issue_user_token() -> tuple:
    """Create a new session: returns (token for the client, internal session id)."""
    session_id = str(uuid.uuid4())
    return _user_id_signer.dumps(session_id), session_id


def verify_user_token(token) -> str:
    """Return the session id inside a token this server issued, else None."""
    if not isinstance(token, str) or not token:
        return None
    try:
        session_id = _user_id_signer.loads(token)
    except BadSignature:
        return None
    return session_id if isinstance(session_id, str) else None

# langdetect is probabilistic; seed it so the same text always gets the same answer.
DetectorFactory.seed = 0

# Hiragana, katakana (incl. half-width) and CJK ideographs.
_JAPANESE_SCRIPT_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")


def detect_language(text: str) -> str:
    """Return a langdetect code for `text`, or "unknown" if it can't tell
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


@dataclass
class ChatResponse:
    """Data class for chat responses"""

    answer: str
    sources: List[SearchResult]
    query: str
    timestamp: str
    tokens_used: int
    file_names: List[str]  # New field to store file names
    related_videos: List[Dict[str, str]] = field(default_factory=list)
    # True when `answer` is an error message; such turns are not saved to history.
    error: bool = False


class OpenAIGenerator:
    """OpenAI GPT integration for generating responses"""

    def __init__(self):
        # Initialize OpenAI v1 client (reads API key from environment)
        self.client = OpenAI()
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    def generate_response(
        self,
        query: str,
        search_results: List[SearchResult],
        conversation_history: List[Dict] = None,
        is_english_input: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate response using OpenAI with search results and conversation history

        Args:
            query: User's question
            search_results: Relevant conversation excerpts from Zilliz
            conversation_history: Previous conversation messages for context
            is_english_input: Whether the original input was in English

        Returns:
            Dictionary containing response and metadata
        """
        try:
            # Prepare context from search results
            context_parts: List[str] = []
            for i, result in enumerate(search_results, 1):
                context_parts.append(
                    f"[Context {i}] Speaker: {result.speaker}\n"
                    f"Content: {result.text}\n"
                    f"Timestamp: {result.timestamp}\n"
                    f"Relevance Score: {result.score:.3f}\n"
                )

            context = "\n".join(context_parts)

            base_prompt = """Answer users' questions from the given user context.

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

            if is_english_input:
                system_prompt = base_prompt + "\n- Answer in English"
            else:
                system_prompt = base_prompt + "\n- Answer in Japanese"

            # Create user prompt
            user_prompt = f"""Question: {query}

Context from relevant conversations:
{context}

Please provide a helpful answer based on the above context.
If the context doesn't contain enough information to answer the question, please say so."""

            # Build messages array with conversation history
            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history if available
            if conversation_history:
                trimmed_history = self._trim_history(conversation_history)
                messages.extend(trimmed_history)

            # Add current query with RAG context
            messages.append({"role": "user", "content": user_prompt})

            # Generate response using OpenAI v1 client
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            except Exception as api_error:
                # Handle token limit exceeded error
                if "maximum context length" in str(api_error).lower():
                    logger.warning("Token limit exceeded, trimming more aggressively")
                    # Retry with more aggressive trimming
                    if conversation_history:
                        trimmed_history = self._trim_history(
                            conversation_history,
                            max_turns=10,
                            max_tokens=2000
                        )
                        messages = [{"role": "system", "content": system_prompt}]
                        messages.extend(trimmed_history)
                        messages.append({"role": "user", "content": user_prompt})

                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                else:
                    raise

            logger.debug(user_prompt)
            # content is None on refusals; never let None reach the session
            # history, where it breaks every later request for this user.
            answer = response.choices[0].message.content or ""
            if not answer.strip():
                raise ValueError("OpenAI returned an empty answer")

            # If English input but Japanese response generated, translate back to English
            if is_english_input and detect_language(answer) == "ja":
                logger.info("Translating response back to English...")
                en_translator = GoogleTranslator(source="ja", target="en")
                answer = en_translator.translate(answer)

            return {
                "answer": answer,
                "tokens_used": getattr(response.usage, "total_tokens", 0),
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error generating OpenAI response: {e}")
            error_message = (
                "Sorry, an error occurred while generating the response."
                if is_english_input
                else "申し訳ございませんが、回答の生成中にエラーが発生しました。"
            )
            return {
                "answer": error_message,
                "tokens_used": 0,
                "model": self.model,
                "error": str(e),
            }

    def _trim_history(
        self,
        history: List[Dict],
        max_turns: int = 20,
        max_tokens: int = 4000
    ) -> List[Dict]:
        """
        Trim conversation history to fit within context window

        Args:
            history: List of conversation messages
            max_turns: Maximum number of turns to keep
            max_tokens: Maximum tokens to keep (approximate)

        Returns:
            Trimmed conversation history
        """
        if not history:
            return []

        # Filter to user/assistant messages only
        conversation = [m for m in history if m["role"] in ["user", "assistant"]]

        # Trim by turns (keep most recent)
        if len(conversation) > max_turns:
            conversation = conversation[-max_turns:]

        # Trim by tokens (approximate: 1 token ≈ 4 characters)
        total_tokens = sum(len(m["content"]) // 4 for m in conversation)
        while total_tokens > max_tokens and len(conversation) > 2:
            removed = conversation.pop(0)
            total_tokens -= len(removed["content"]) // 4

        return conversation


class ChatService:
    """Main chat service combining Zilliz search and OpenAI generation"""

    def __init__(self):
        # ConversationVectorizer provides BM25 hybrid search (dense + native BM25 sparse)
        zilliz_uri = os.getenv("ZILLIZ_URI")
        zilliz_token = os.getenv("ZILLIZ_TOKEN")
        self.vectorizer = ConversationVectorizer(zilliz_uri, zilliz_token)

        self.ai_generator = OpenAIGenerator()
        # Small, fast model for the follow-up check / query rewrite that runs
        # before every search; the answer itself still uses OPENAI_MODEL.
        self.rewrite_model = os.getenv("OPENAI_REWRITE_MODEL", "gpt-4.1-mini")
        self.translator = GoogleTranslator(source="auto", target="ja")

    def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        """
        Search relevant passages: BM25 hybrid search, best chunk per video,
        optional reranking, then each hit widened with its neighbouring chunks
        so a story's set-up and punchline reach the answer together.
        """
        return self.vectorizer.search_passages(query, limit=limit)

    # How much recent history the follow-up classifier sees. Only the latest
    # turns matter for deciding "is this a continuation?", and capping each
    # message keeps the extra LLM call small and fast.
    REWRITE_HISTORY_MESSAGES = 4  # = last 2 user/assistant turns
    REWRITE_MESSAGE_CHARS = 500

    REWRITE_SYSTEM_PROMPT = """You decide whether a user's new question continues the previous conversation, and rewrite it as a standalone search query.

Return JSON only, in this exact shape:
{"is_follow_up": true or false, "standalone_query": "..."}

Rules:
- is_follow_up = true only if the new question cannot be fully understood without the conversation (pronouns like "それ", "その動画", "さっきの", "もっと詳しく", or an obvious continuation of the same topic).
- is_follow_up = false if the question is understandable on its own or changes the topic, even if it is in the same broad area.
- If is_follow_up is true, standalone_query must be one self-contained question with pronouns and omitted subjects replaced by the concrete topic from the conversation.
- If is_follow_up is false, standalone_query must be the new question unchanged.
- Write standalone_query in Japanese (the search index is Japanese). Do not answer the question."""

    def analyze_query(
        self, query: str, conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Ask a small LLM whether `query` continues the conversation and, if
        so, rewrite it into a self-contained search query.

        Returns {"is_follow_up": bool, "search_query": str}. With no history
        there is nothing to continue, so the LLM is not called. If the LLM
        call fails or returns malformed JSON, the original query is used for
        search and history is still passed to answer generation (the previous
        default), so a classifier outage never breaks chat.
        """
        conversation = [
            m for m in (conversation_history or []) if m.get("role") in ("user", "assistant")
        ]
        if not conversation:
            return {"is_follow_up": False, "search_query": query}

        recent = conversation[-self.REWRITE_HISTORY_MESSAGES:]
        history_text = "\n".join(
            f"{m['role']}: {m['content'][: self.REWRITE_MESSAGE_CHARS]}" for m in recent
        )
        user_content = f"Conversation:\n{history_text}\n\nNew question: {query}"

        try:
            response = self.ai_generator.client.chat.completions.create(
                model=self.rewrite_model,
                messages=[
                    {"role": "system", "content": self.REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
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
            if not isinstance(standalone, str) or not standalone.strip():
                standalone = query
        except Exception as e:
            logger.warning(f"Follow-up analysis failed, using original query: {e}")
            return {"is_follow_up": True, "search_query": query}

        search_query = standalone.strip() if is_follow_up else query
        logger.info(
            f"Follow-up analysis: is_follow_up={is_follow_up}, search_query={search_query!r}"
        )
        return {"is_follow_up": is_follow_up, "search_query": search_query}

    def get_related_videos(self, search_results: List[SearchResult]) -> List[Dict[str, str]]:
        """
        Build the "Related" video list directly from each SearchResult's
        title (stored in the Zilliz collection at ingestion time), deduplicated
        by video_id. Falls back to the video_id itself if a chunk predates the
        title field.
        """
        seen = {}
        for result in search_results:
            video_id = re.sub(r"(_transcription)?\.json$", "", result.file_name)
            if video_id not in seen:
                seen[video_id] = {
                    "video_id": video_id,
                    "title": result.title or video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
        return list(seen.values())

    def process_chat_query(
        self,
        query: str,
        user_id: str = None,
        conversation_history: List[Dict] = None,
        max_results: int = 5
    ) -> ChatResponse:
        """
        Process a chat query with RAG (Retrieval-Augmented Generation) and conversation history

        Args:
            query: User's question
            user_id: User identifier for tracking
            conversation_history: Previous conversation messages for context
            max_results: Maximum number of search results to use

        Returns:
            ChatResponse with answer and sources
        """
        try:
            # Detect language for response formatting
            original_query = query
            is_english_input = not is_japanese_query(query)

            if is_english_input:
                logger.info(
                    "Detected English prompt. Translating to Japanese for search..."
                )
                query = self.translator.translate(query)
                logger.info(f"Translated prompt for search: {query}")

            # Decide whether this question continues the conversation. Follow-ups
            # are searched with an LLM-rewritten standalone query; a new topic is
            # searched as-is and answered without the previous history, so an
            # old topic can't leak into retrieval or the answer.
            analysis = self.analyze_query(query, conversation_history)
            search_results = self.search(analysis["search_query"], limit=max_results)
            history_for_answer = (
                (conversation_history or []) if analysis["is_follow_up"] else []
            )

            ai_response = self.ai_generator.generate_response(
                query=query,
                search_results=search_results,
                conversation_history=history_for_answer,
                is_english_input=is_english_input
            )

            # Collect file names from search results
            file_names = list({result.file_name for result in search_results})
            related_videos = self.get_related_videos(search_results)

            # Create chat response
            chat_response = ChatResponse(
                answer=ai_response["answer"],
                sources=search_results,
                query=original_query,  # Use original query in response
                timestamp=datetime.now().isoformat(),
                tokens_used=ai_response["tokens_used"],
                file_names=file_names,  # Include file names
                related_videos=related_videos,
                error="error" in ai_response,
            )

            return chat_response

        except Exception as e:
            logger.error(f"Error processing chat query: {e}")
            error_message = (
                "Sorry, an error occurred during processing."
                if "is_english_input" in locals() and is_english_input
                else "申し訳ございませんが、処理中にエラーが発生しました。"
            )
            return ChatResponse(
                answer=error_message,
                sources=[],
                query=original_query if "original_query" in locals() else query,
                timestamp=datetime.now().isoformat(),
                tokens_used=0,
                file_names=[],  # Return empty file names on error
                error=True,
            )


# Initialize chat service and session manager
chat_service = ChatService()
session_manager = SessionManager()


# Flask Routes
@app.route("/")
def index():
    """Serve the chat interface"""
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """REST API endpoint for chat with session memory"""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()

        # Only a server-issued user_id continues a session. A missing, made-up
        # or tampered one starts a new session, so nobody can chat with (and
        # have answers drawn from) another user's history.
        user_token = data.get("user_id")
        user_id = verify_user_token(user_token)
        if user_id is None:
            user_token, user_id = issue_user_token()

        logger.info(f"API /api/chat received query from {user_id}: {query}")

        if not query:
            return Response(
                json.dumps({"error": "Query is required"}, ensure_ascii=False),
                mimetype="application/json",
                status=400,
            )

        # Get conversation history
        conversation_history = session_manager.get_history_for_openai(user_id)

        # Process chat query with history
        response = chat_service.process_chat_query(
            query=query,
            user_id=user_id,
            conversation_history=conversation_history
        )

        # Save the exchange, unless the answer is an error message: that would
        # become "context" for the next turn.
        if not response.error:
            session_manager.add_message(user_id, "user", query, tokens=len(query) // 4)
            # Count the answer's own size, not response.tokens_used (the whole
            # call incl. RAG context), or the trimmer drops all but the last
            # exchange.
            session_manager.add_message(
                user_id,
                "assistant",
                response.answer,
                tokens=len(response.answer) // 4
            )

        response_dict = {
            "answer": response.answer,
            "sources": [
                {
                    "text": source.text,
                    "speaker": source.speaker,
                    "timestamp": source.timestamp,
                    "score": source.score,
                    "file_name": source.file_name,
                }
                for source in response.sources
            ],
            "query": response.query,
            "timestamp": response.timestamp,
            "tokens_used": response.tokens_used,
            "file_names": response.file_names,
            "related_videos": response.related_videos,
            "user_id": user_token,  # send this back to continue the session
        }
        return Response(
            json.dumps(response_dict, ensure_ascii=False), mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"API chat error: {e}")
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status=500,
        )


MAX_SEARCH_LIMIT = 20


@app.route("/api/search", methods=["POST"])
def api_search():
    """REST API endpoint for conversation search only"""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        limit = data.get("limit", 5)

        logger.info(f"API /api/search received query: {query} (limit={limit})")

        if not query:
            return jsonify({"error": "Query is required"}), 400

        # bool is an int subclass; reject it along with strings/floats.
        if isinstance(limit, bool) or not isinstance(limit, int) or not (
            1 <= limit <= MAX_SEARCH_LIMIT
        ):
            return jsonify(
                {"error": f"limit must be an integer from 1 to {MAX_SEARCH_LIMIT}"}
            ), 400

        # Search conversations using the configured backend (dense + sparse)
        results = chat_service.search(query, limit)

        return jsonify(
            {
                "query": query,
                "results": [
                    {
                        "text": result.text,
                        "speaker": result.speaker,
                        "timestamp": result.timestamp,
                        "score": result.score,
                        "file_name": result.file_name,
                    }
                    for result in results
                ],
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/clear", methods=["POST"])
def api_clear_session():
    """Clear conversation history for user"""
    try:
        data = request.get_json()
        user_token = data.get("user_id")

        if not user_token:
            return jsonify({"error": "user_id is required"}), 400

        user_id = verify_user_token(user_token)
        if user_id is None:
            return jsonify({"error": "invalid user_id"}), 403

        session_manager.clear_session(user_id)

        return jsonify({
            "status": "success",
            "message": "Session cleared"
        })

    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/export", methods=["POST"])
def api_export_session():
    """Export conversation history for user"""
    try:
        data = request.get_json()
        user_token = data.get("user_id")

        if not user_token:
            return jsonify({"error": "user_id is required"}), 400

        user_id = verify_user_token(user_token)
        if user_id is None:
            return jsonify({"error": "invalid user_id"}), 403

        session = session_manager.get_session(user_id)

        if not session:
            return jsonify({"error": "No session found"}), 404

        return jsonify({
            "user_id": user_token,
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
            "total_tokens": session.total_tokens,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tokens": msg.tokens
                }
                for msg in session.messages
            ]
        })

    except Exception as e:
        logger.error(f"Error exporting session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/stats", methods=["GET"])
def api_session_stats():
    """Get session manager statistics"""
    try:
        stats = session_manager.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_check():
    """Health check endpoint"""
    session_stats = session_manager.get_stats()
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "zilliz": (
                    "connected"
                    if chat_service.vectorizer.bm25_client
                    and chat_service.vectorizer.bm25_client.collection
                    else "disconnected"
                ),
                "openai": (
                    "configured"
                    if bool(os.getenv("OPENAI_API_KEY"))
                    else "not configured"
                ),
                "session_storage": session_stats.get("storage_type", "unknown"),
                "active_sessions": session_stats.get("active_sessions", 0),
            },
        }
    )


# Socket.IO Events
@socketio.on("connect")
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit("status", {"message": "Connected to chat server"})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("chat_message")
def handle_chat_message(data):
    """Handle chat message via WebSocket with session memory"""
    try:
        query = data.get("query", "").strip()
        user_id = request.sid  # Use socket session ID as user_id

        if not query:
            emit("chat_error", {"error": "Query is required"})
            return

        logger.info(f"Processing chat query from {user_id}: {query}")

        # Get conversation history
        conversation_history = session_manager.get_history_for_openai(user_id)

        # Process chat query with history
        response = chat_service.process_chat_query(
            query=query,
            user_id=user_id,
            conversation_history=conversation_history
        )

        # Add to session (error replies are not saved as history)
        if not response.error:
            session_manager.add_message(user_id, "user", query, tokens=len(query) // 4)
            session_manager.add_message(
                user_id,
                "assistant",
                response.answer,
                tokens=len(response.answer) // 4  # answer size, not whole-call usage
            )

        # Send response
        emit(
            "chat_response",
            {
                "answer": response.answer,
                "sources": [
                    {
                        "text": source.text,
                        "speaker": source.speaker,
                        "timestamp": source.timestamp,
                        "score": source.score,
                        "file_name": source.file_name,
                    }
                    for source in response.sources
                ],
                "query": response.query,
                "timestamp": response.timestamp,
                "tokens_used": response.tokens_used,
                "file_names": response.file_names,
                "related_videos": response.related_videos,
            },
        )

    except Exception as e:
        logger.error(f"WebSocket chat error: {e}")
        emit("chat_error", {"error": str(e)})


if __name__ == "__main__":
    """Run the Flask chat server"""
    # Hugging Face Spaces対応: デフォルトポートを7860に変更
    port = int(os.getenv("FLASK_PORT", 7860))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    logger.info(f"Starting Flask chat server on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Environment: {'Development' if debug else 'Production'}")

    # This app is served directly by Flask-SocketIO's built-in Werkzeug server
    # (no separate WSGI/ASGI server in front of it), so allow_unsafe_werkzeug
    # must stay True even outside debug mode - otherwise socketio.run() raises
    # RuntimeError and the server never starts.
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
    )
