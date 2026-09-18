"""
Flask Chat Server with Zilliz Cloud and OpenAI Integration
Provides RAG (Retrieval-Augmented Generation) functionality for conversation search
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from openai import OpenAI
from dotenv import load_dotenv
from langdetect import detect
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


@dataclass
class ChatResponse:
    """Data class for chat responses"""

    answer: str
    sources: List[SearchResult]
    query: str
    timestamp: str
    tokens_used: int
    file_names: List[str]  # New field to store file names


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
            sentence breaks. Read through the run-on text carefully and infer the
            intended meaning; do not require an exact literal phrase match before
            treating the context as relevant. If the context clearly implies an
            answer (even indirectly), answer with that inference instead of saying
            the information is missing.

            Guidelines:
            - Answer casually in a natural conversational tone
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

            print(user_prompt)
            answer = response.choices[0].message.content

            # If English input but Japanese response generated, translate back to English
            if is_english_input and detect(answer) == "ja":
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
        self.translator = GoogleTranslator(source="auto", target="ja")

    def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Search relevant conversation chunks via BM25 hybrid search"""
        return self.vectorizer.hybrid_search_bm25(query, limit=limit)

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
            detected_language = detect(query)
            is_english_input = detected_language != "ja"

            if is_english_input:
                logger.info(
                    "Detected English prompt. Translating to Japanese for search..."
                )
                query = self.translator.translate(query)
                logger.info(f"Translated prompt for search: {query}")

            # Search for relevant conversations via native Zilliz BM25 hybrid search
            search_results = self.search(query, limit=max_results)

            # Generate AI response with conversation history
            ai_response = self.ai_generator.generate_response(
                query=query,
                search_results=search_results,
                conversation_history=conversation_history or [],
                is_english_input=is_english_input
            )

            # Collect file names from search results
            file_names = list({result.file_name for result in search_results})

            # Create chat response
            chat_response = ChatResponse(
                answer=ai_response["answer"],
                sources=search_results,
                query=original_query,  # Use original query in response
                timestamp=datetime.now().isoformat(),
                tokens_used=ai_response["tokens_used"],
                file_names=file_names,  # Include file names
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
        user_id = data.get("user_id", str(uuid.uuid4()))

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

        # Add user message to history
        session_manager.add_message(user_id, "user", query, tokens=len(query) // 4)

        # Add assistant response to history
        session_manager.add_message(
            user_id,
            "assistant",
            response.answer,
            tokens=response.tokens_used
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
            "user_id": user_id,  # Return user_id for client tracking
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
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        session_manager.clear_session(user_id)

        return jsonify({
            "status": "success",
            "message": f"Session cleared for {user_id}"
        })

    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/export", methods=["POST"])
def api_export_session():
    """Export conversation history for user"""
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        session = session_manager.get_session(user_id)

        if not session:
            return jsonify({"error": "No session found"}), 404

        return jsonify({
            "user_id": session.user_id,
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

        # Add to session
        session_manager.add_message(user_id, "user", query, tokens=len(query) // 4)
        session_manager.add_message(
            user_id,
            "assistant",
            response.answer,
            tokens=response.tokens_used
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

    # Hugging Face Spaces対応: 本番環境ではallow_unsafe_werkzeugをFalseに
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=debug,  # debugモードの時のみTrue
    )
