"""
Flask chat server: RAG answers over past conversations.

Serves ChatService (services/chat/service.py) over REST (/api/*) and
Socket.IO ("chat_message"), and keeps each user's conversation in a session.

Run with `python api/chat_server.py` (from src/), or via run_chat_server.py.
"""

import hmac
import logging
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv
from flask import Blueprint, Flask, current_app, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.exceptions import HTTPException

from api.auth import UserTokens
from models.conversation_chunk import SearchResult
from services.chat.prompt_store import Prompt, PromptStore, default_prompt_id, default_store_dir
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
    # Answer prompts users choose from. None: built in create_app() from
    # PROMPT_STORE_DIR / ANSWER_PROMPT.
    prompts: Optional[PromptStore] = None
    # Password for the prompt editor (/admin/prompts). None disables editing.
    admin_token: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Services":
        # ChatService connects to Zilliz and loads the embedding model.
        return cls(ChatService(), SessionManager(), UserTokens.from_env(),
                   admin_token=os.getenv("ADMIN_TOKEN") or None)


def services() -> Services:
    return current_app.extensions["chat_server"]


def create_app(app_services: Optional[Services] = None) -> Tuple[Flask, SocketIO]:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.json.ensure_ascii = False  # keep Japanese readable in JSON responses
    app_services = app_services or Services.from_env()
    if app_services.prompts is None:
        provider = app_services.chat.llm_info["provider"]
        app_services.prompts = PromptStore(default_store_dir(), default_prompt_id(provider))
    logger.info(f"Prompt store: {app_services.prompts.directory} (default: {app_services.prompts.default_id})")
    if not app_services.admin_token:
        logger.info("Prompt editor disabled: set ADMIN_TOKEN to enable /admin/prompts")
    app.extensions["chat_server"] = app_services
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


def run_chat_turn(
    session_id: str, query: str, prompt_id: Optional[str] = None
) -> Tuple[ChatResponse, Prompt]:
    """Answer `query` in `session_id`'s conversation with the chosen answer
    prompt (the default if `prompt_id` is missing or unknown), and save the
    exchange. Returns the response and the prompt actually used.

    Error replies are not saved: they would become "context" for the next turn.
    """
    prompt = services().prompts.resolve(prompt_id)
    sessions = services().sessions
    history = sessions.get_history_for_openai(session_id)
    response = services().chat.process_chat_query(query, history, system_prompt=prompt.text)
    if not response.error:
        # Count each message's own size. response.tokens_used covers the whole
        # call (incl. RAG context); storing it makes the session trimmer drop
        # all but the last exchange.
        sessions.add_message(session_id, "user", query, tokens=len(query) // 4)
        sessions.add_message(
            session_id, "assistant", response.answer, tokens=len(response.answer) // 4
        )
    return response, prompt


def source_to_dict(result: SearchResult) -> Dict:
    return {
        "text": result.text,
        "speaker": result.speaker,
        "timestamp": result.timestamp,
        "score": result.score,
        "file_name": result.file_name,
    }


def chat_response_to_dict(response: ChatResponse, prompt: Prompt) -> Dict:
    return {
        "answer": response.answer,
        "sources": [source_to_dict(s) for s in response.sources],
        "query": response.query,
        "timestamp": response.timestamp,
        "tokens_used": response.tokens_used,
        "file_names": response.file_names,
        "related_videos": response.related_videos,
        "prompt_id": prompt.id,
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
    response, prompt = run_chat_turn(session_id, query, data.get("prompt_id"))
    return jsonify({**chat_response_to_dict(response, prompt), "user_id": user_token})


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


# --- Answer prompts: anyone can list and choose; editing needs ADMIN_TOKEN ---


@bp.get("/api/prompts")
def api_list_prompts():
    """Prompts for the chat screen's selector (titles only, not the text)."""
    store = services().prompts
    return jsonify({
        "prompts": [{"id": p.id, "title": p.title} for p in store.list()],
        "default": store.default_id,
    })


def require_admin(view):
    """Allow the request only with `Authorization: Bearer <ADMIN_TOKEN>`."""

    @wraps(view)
    def guarded(*args, **kwargs):
        expected = services().admin_token
        if not expected:
            raise ApiError(403, "Prompt editing is disabled: set ADMIN_TOKEN on the server")
        header = request.headers.get("Authorization", "")
        given = header[len("Bearer "):] if header.startswith("Bearer ") else ""
        if not hmac.compare_digest(given.encode(), expected.encode()):
            raise ApiError(401, "Invalid admin token")
        return view(*args, **kwargs)

    return guarded


def prompt_to_admin_dict(prompt: Prompt) -> Dict:
    return {
        "id": prompt.id,
        "title": prompt.title,
        "text": prompt.text,
        "builtin": prompt.builtin,  # read-only
    }


@bp.get("/admin/prompts")
def admin_prompts_page():
    return render_template("admin_prompts.html")


@bp.get("/api/admin/prompts")
@require_admin
def api_admin_list_prompts():
    store = services().prompts
    return jsonify({
        "prompts": [prompt_to_admin_dict(p) for p in store.list()],
        "default": store.default_id,
        "store": str(store.directory),
    })


@bp.put("/api/admin/prompts/<prompt_id>")
@require_admin
def api_admin_save_prompt(prompt_id: str):
    """Create or replace an admin prompt (built-ins are read-only)."""
    data = json_body()
    existing = services().prompts.get(prompt_id)
    if existing and existing.builtin:
        raise ApiError(403, "Built-in prompts can't be edited; save your version under a new id")
    try:
        prompt = services().prompts.save(prompt_id, data.get("title"), data.get("text"))
    except ValueError as e:
        raise ApiError(400, str(e))
    return jsonify(prompt_to_admin_dict(prompt))


@bp.delete("/api/admin/prompts/<prompt_id>")
@require_admin
def api_admin_delete_prompt(prompt_id: str):
    """Delete an admin prompt (built-ins can't be deleted)."""
    try:
        services().prompts.delete(prompt_id)
    except KeyError:
        raise ApiError(404, "No deletable prompt with that id (built-ins can't be deleted)")
    return jsonify({"status": "deleted", "default": services().prompts.default_id})


@bp.put("/api/admin/default-prompt")
@require_admin
def api_admin_set_default_prompt():
    prompt_id = json_body().get("id")
    try:
        services().prompts.set_default(prompt_id)
    except KeyError:
        raise ApiError(404, "No prompt with that id")
    return jsonify({"default": prompt_id})


@bp.get("/health")
def health_check():
    session_stats = services().sessions.get_stats()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "zilliz": "connected" if services().chat.is_search_connected else "disconnected",
            "llm": services().chat.llm_info,
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
        response, prompt = run_chat_turn(session_id, query, data.get("prompt_id"))
    except Exception:
        logger.exception("WebSocket chat error")
        emit("chat_error", {"error": "Internal server error"})
        return
    emit("chat_response", chat_response_to_dict(response, prompt))


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
