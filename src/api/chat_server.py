"""
Flask chat server: RAG answers over past conversations.

Serves ChatService (services/chat/service.py) over REST (/api/*) and
Socket.IO ("chat_message"), and keeps each user's conversation in a session.

Run with `python api/chat_server.py` (from src/), or via run_chat_server.py.
"""

import logging
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv
from flask import Blueprint, Flask, current_app, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.exceptions import HTTPException

from api.auth import UserTokens
from models.conversation_chunk import SearchResult
from services.chat.service import DEFAULT_SEARCH_LIMIT, ChatResponse, ChatService
from services.session.session_manager import SessionManager

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

MAX_SEARCH_LIMIT = 20


@dataclass
class Services:
    """What the routes use; create_app() takes these so tests can pass fakes."""

    chat: ChatService
    sessions: SessionManager
    tokens: UserTokens

    @classmethod
    def from_env(cls) -> "Services":
        # ChatService connects to Zilliz and loads the embedding model.
        return cls(ChatService(), SessionManager(), UserTokens.from_env())


def services() -> Services:
    return current_app.extensions["chat_server"]


def create_app(app_services: Optional[Services] = None) -> Tuple[Flask, SocketIO]:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.json.ensure_ascii = False  # keep Japanese readable in JSON responses
    app.extensions["chat_server"] = app_services or Services.from_env()
    CORS(app)
    app.register_blueprint(bp)

    # threading mode: eventlet/gevent don't support Python 3.13+
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    socketio.on_event("connect", handle_connect)
    socketio.on_event("disconnect", handle_disconnect)
    socketio.on_event("chat_message", handle_chat_message)
    return app, socketio


# ---------------------------------------------------------------------------
# Shared by REST and Socket.IO
# ---------------------------------------------------------------------------


def run_chat_turn(session_id: str, query: str) -> ChatResponse:
    """Answer `query` in `session_id`'s conversation and save the exchange.

    Error replies are not saved: they would become "context" for the next turn.
    """
    sessions = services().sessions
    history = sessions.get_history_for_openai(session_id)
    response = services().chat.process_chat_query(query, history)
    if not response.error:
        # Count each message's own size. response.tokens_used covers the whole
        # call (incl. RAG context); storing it makes the session trimmer drop
        # all but the last exchange.
        sessions.add_message(session_id, "user", query, tokens=len(query) // 4)
        sessions.add_message(
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


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

bp = Blueprint("chat", __name__)


class ApiError(Exception):
    """A client error, returned as {"error": message} with `status`."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@bp.app_errorhandler(ApiError)
def handle_api_error(e: ApiError):
    return jsonify({"error": e.message}), e.status


@bp.app_errorhandler(Exception)
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
    session_id = services().tokens.verify(token)
    if session_id is None:
        raise ApiError(403, "invalid user_id")
    return session_id


@bp.get("/")
def index():
    return render_template("chat.html")


@bp.post("/api/chat")
def api_chat():
    """Chat with session memory. Send back the returned user_id to continue
    the session; a missing, made-up or tampered one starts a new session."""
    data = json_body()
    query = required_query(data)

    user_token = data.get("user_id")
    session_id = services().tokens.verify(user_token)
    if session_id is None:
        user_token, session_id = services().tokens.issue()

    logger.info(f"API /api/chat received query from {session_id}: {query}")
    response = run_chat_turn(session_id, query)
    return jsonify({**chat_response_to_dict(response), "user_id": user_token})


@bp.post("/api/search")
def api_search():
    """Search only, no answer generation."""
    data = json_body()
    query = required_query(data)
    limit = data.get("limit", DEFAULT_SEARCH_LIMIT)
    # bool is an int subclass; reject it along with strings/floats.
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ApiError(400, f"limit must be an integer from 1 to {MAX_SEARCH_LIMIT}")

    logger.info(f"API /api/search received query: {query} (limit={limit})")
    results = services().chat.search(query, limit)
    return jsonify({
        "query": query,
        "results": [source_to_dict(r) for r in results],
        "timestamp": datetime.now().isoformat(),
    })


@bp.post("/api/session/clear")
def api_clear_session():
    services().sessions.clear_session(verified_session_id(json_body()))
    return jsonify({"status": "success", "message": "Session cleared"})


@bp.post("/api/session/export")
def api_export_session():
    data = json_body()
    session = services().sessions.get_session(verified_session_id(data))
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


@bp.get("/api/session/stats")
def api_session_stats():
    return jsonify(services().sessions.get_stats())


@bp.get("/health")
def health_check():
    session_stats = services().sessions.get_stats()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "zilliz": "connected" if services().chat.is_search_connected else "disconnected",
            "openai": "configured" if os.getenv("OPENAI_API_KEY") else "not configured",
            "session_storage": session_stats.get("storage_type", "unknown"),
            "active_sessions": session_stats.get("active_sessions", 0),
        },
    })


# ---------------------------------------------------------------------------
# Socket.IO (registered in create_app)
# ---------------------------------------------------------------------------


def handle_connect(auth=None):
    logger.info(f"Client connected: {request.sid}")
    emit("status", {"message": "Connected to chat server"})


def handle_disconnect(reason=None):
    logger.info(f"Client disconnected: {request.sid}")


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


# Module-level app: `python api/chat_server.py` and run_chat_server.py
# (`from api.chat_server import app, socketio`) both use it.
app, socketio = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 7860))  # 7860: Hugging Face Spaces
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    logger.info(f"Starting Flask chat server on port {port} (debug={debug})")

    # Served directly by Flask-SocketIO's built-in Werkzeug server (no
    # separate WSGI/ASGI server in front of it), so allow_unsafe_werkzeug must
    # stay True even outside debug mode, or socketio.run() refuses to start.
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True)
