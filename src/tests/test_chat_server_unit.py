"""
Offline tests for the REST routes and Socket.IO handlers in api/chat_server.py.

Each test gets its own app from create_app() with a fake ChatService
backend, in-memory sessions and a fixed token key. Importing chat_server
also builds a module-level app, so the import itself runs with Zilliz,
.env and Redis stubbed out.
"""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.chat.service as service_module
from api.auth import UserTokens
from models.conversation_chunk import SearchResult
from services.chat.generator import GeneratedAnswer
from services.chat.service import ChatService, QueryAnalysis
from services.session.session_manager import SessionManager


@pytest.fixture(scope="module")
def chat_server():
    saved = sys.modules.pop("api.chat_server", None)
    mp = pytest.MonkeyPatch()
    mp.setattr(service_module, "ConversationVectorizer", MagicMock(name="ConversationVectorizer"))
    mp.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # don't read the real .env
    mp.setenv("OPENAI_API_KEY", "test-key")  # OpenAI() needs a key; no call is made
    mp.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> memory storage
    try:
        module = importlib.import_module("api.chat_server")
    finally:
        mp.undo()
    yield module
    if saved is not None:
        sys.modules["api.chat_server"] = saved


def _result():
    return SearchResult(
        text="駅そばの話", speaker="A", timestamp="00:01", file_name="abc123.json",
        score=0.9, similarity=0.9, search_type="hybrid", title="Video",
    )


@pytest.fixture
def server(chat_server, monkeypatch):
    """A fresh app whose chat backend answers "答えです" from one search result."""
    vectorizer = MagicMock()
    vectorizer.search_passages.return_value = [_result()]
    generator = MagicMock()
    generator.generate.return_value = GeneratedAnswer("答えです", 10)
    chat = ChatService(vectorizer=vectorizer, generator=generator, translator=MagicMock())
    # Treat every question as a follow-up searched as asked.
    monkeypatch.setattr(chat, "analyze_query", lambda q, h: QueryAnalysis(True, q))

    sessions = SessionManager()
    sessions.storage_type, sessions.memory_store = "memory", {}
    tokens = UserTokens("test-secret")

    app, socketio = chat_server.create_app(chat_server.Services(chat, sessions, tokens))
    return SimpleNamespace(
        app=app, socketio=socketio, client=app.test_client(),
        chat=chat, vectorizer=vectorizer, generator=generator,
        sessions=sessions, tokens=tokens,
    )


def history_of(server, token):
    return server.sessions.get_history_for_openai(server.tokens.verify(token))


# --- /api/chat and sessions -------------------------------------------------

def test_chat_returns_answer_sources_and_a_token(server):
    body = server.client.post("/api/chat", json={"query": " 駅そば "}).get_json()

    assert body["answer"] == "答えです"
    assert body["query"] == "駅そば"
    assert body["sources"] == [{
        "text": "駅そばの話", "speaker": "A", "timestamp": "00:01", "score": 0.9, "file_name": "abc123.json",
    }]
    assert body["related_videos"][0]["video_id"] == "abc123"
    assert server.tokens.verify(body["user_id"]) is not None


def test_session_keeps_history_when_calls_use_many_tokens(server):
    # Each call reports far more than MAX_CONVERSATION_TOKENS (default 4000).
    server.generator.generate.return_value = GeneratedAnswer("答えです", 9000)

    token = None
    for q in ["一つ目の質問", "二つ目の質問", "三つ目の質問"]:
        body = {"query": q} if token is None else {"query": q, "user_id": token}
        res = server.client.post("/api/chat", json=body)
        assert res.status_code == 200
        token = res.get_json()["user_id"]

    history = history_of(server, token)
    assert [m["content"] for m in history if m["role"] == "user"] == [
        "一つ目の質問", "二つ目の質問", "三つ目の質問",
    ]
    assert len(history) == 6


def test_made_up_user_id_cannot_join_existing_session(server):
    # The victim's session is stored under its raw id.
    server.sessions.add_message("victim", "user", "秘密の話", tokens=1)

    res = server.client.post("/api/chat", json={"query": "さっきの話は？", "user_id": "victim"})

    assert res.status_code == 200
    new_token = res.get_json()["user_id"]
    assert new_token != "victim"
    assert server.tokens.verify(new_token) != "victim"
    assert len(server.sessions.get_history_for_openai("victim")) == 1  # untouched


@pytest.mark.parametrize("endpoint", ["/api/session/export", "/api/session/clear"])
def test_session_endpoints_reject_unissued_user_id(server, endpoint):
    server.sessions.add_message("victim", "user", "秘密の話", tokens=1)

    res = server.client.post(endpoint, json={"user_id": "victim"})

    assert res.status_code == 403
    assert "秘密の話" not in res.get_data(as_text=True)
    assert len(server.sessions.get_history_for_openai("victim")) == 1


@pytest.mark.parametrize("endpoint", ["/api/session/export", "/api/session/clear"])
def test_session_endpoints_require_user_id(server, endpoint):
    res = server.client.post(endpoint, json={})
    assert (res.status_code, res.get_json()) == (400, {"error": "user_id is required"})


def test_export_and_clear_work_with_issued_token(server):
    token = server.client.post("/api/chat", json={"query": "こんにちは"}).get_json()["user_id"]

    export = server.client.post("/api/session/export", json={"user_id": token})
    assert export.status_code == 200
    assert export.get_json()["user_id"] == token
    assert [m["content"] for m in export.get_json()["messages"]] == ["こんにちは", "答えです"]

    assert server.client.post("/api/session/clear", json={"user_id": token}).status_code == 200
    assert server.client.post("/api/session/export", json={"user_id": token}).status_code == 404


def test_error_reply_is_not_saved_to_history(server):
    server.generator.generate.side_effect = RuntimeError("openai down")

    body = server.client.post("/api/chat", json={"query": "こんにちは"}).get_json()

    assert body["answer"] == "申し訳ございませんが、回答の生成中にエラーが発生しました。"
    assert history_of(server, body["user_id"]) == []


def test_search_outage_returns_error_not_a_made_up_answer(server):
    """If Zilliz is down, the user gets an error, not an answer built from no context."""
    server.vectorizer.search_passages.side_effect = ConnectionError("zilliz down")

    res = server.client.post("/api/chat", json={"query": "駅そばの話は？"})

    assert res.status_code == 200
    body = res.get_json()
    assert "エラー" in body["answer"]
    assert body["sources"] == []
    server.generator.generate.assert_not_called()
    assert history_of(server, body["user_id"]) == []


# --- /api/search ------------------------------------------------------------

@pytest.mark.parametrize("limit", ["5", 0, -1, 21, 100000, 2.5, True, None])
def test_search_rejects_bad_limit(server, limit):
    res = server.client.post("/api/search", json={"query": "駅そば", "limit": limit})

    assert res.status_code == 400
    server.vectorizer.search_passages.assert_not_called()


@pytest.mark.parametrize("body, expected", [({}, 5), ({"limit": 1}, 1), ({"limit": 20}, 20)])
def test_search_accepts_valid_limit(server, body, expected):
    res = server.client.post("/api/search", json={"query": "駅そば", **body})

    assert res.status_code == 200
    assert res.get_json()["results"][0]["text"] == "駅そばの話"
    server.vectorizer.search_passages.assert_called_once_with("駅そば", limit=expected)


# --- request validation and error responses ---------------------------------

@pytest.mark.parametrize("path", ["/api/chat", "/api/search", "/api/session/clear", "/api/session/export"])
@pytest.mark.parametrize("body, content_type", [
    ("not json", "text/plain"),
    ("[1, 2]", "application/json"),
    ("null", "application/json"),
    ("{broken", "application/json"),
])
def test_non_object_body_is_400(server, path, body, content_type):
    res = server.client.post(path, data=body, content_type=content_type)

    assert res.status_code == 400
    assert res.get_json() == {"error": "Request body must be a JSON object"}


@pytest.mark.parametrize("query", [123, None, ["駅そば"], "   "])
def test_non_string_or_blank_query_is_400(server, query):
    res = server.client.post("/api/chat", json={"query": query})

    assert res.status_code == 400
    assert res.get_json() == {"error": "Query is required"}


def test_unexpected_error_hides_details(server):
    server.vectorizer.search_passages.side_effect = ConnectionError("zilliz down at in03-secret-host:19530")

    res = server.client.post("/api/search", json={"query": "駅そば"})

    assert res.status_code == 500
    assert res.get_json() == {"error": "Internal server error"}
    assert "secret-host" not in res.get_data(as_text=True)


def test_unknown_route_is_still_404(server):
    assert server.client.get("/no-such-page").status_code == 404
    assert server.client.get("/api/chat").status_code == 405  # POST only


def test_json_keeps_japanese_readable(server):
    raw = server.client.post("/api/chat", json={"query": "こんにちは"}).get_data(as_text=True)
    assert "答えです" in raw  # not \\u7b54...


def test_health_reports_services(server):
    server.vectorizer.bm25_client = SimpleNamespace(collection=object())
    services = server.client.get("/health").get_json()["services"]
    assert services["zilliz"] == "connected"
    assert services["session_storage"] == "memory"

    server.vectorizer.bm25_client = None
    assert server.client.get("/health").get_json()["services"]["zilliz"] == "disconnected"


# --- Socket.IO --------------------------------------------------------------

def _socket_events(server, *payloads):
    sc = server.socketio.test_client(server.app)
    for p in payloads:
        sc.emit("chat_message", p)
    events = sc.get_received()
    sc.disconnect()
    return [(e["name"], e["args"][0]) for e in events if e["name"] != "status"]


def test_socket_chat_answers_and_remembers(server):
    ((name, payload),) = _socket_events(server, {"query": " 駅そば "})

    assert name == "chat_response"
    assert payload["answer"] == "答えです"
    assert payload["sources"][0]["text"] == "駅そばの話"
    assert "user_id" not in payload  # the socket connection is the session
    (session_id,) = server.sessions.memory_store
    assert [m["content"] for m in server.sessions.get_history_for_openai(session_id)] == ["駅そば", "答えです"]


@pytest.mark.parametrize("payload", [None, "駅そば", {}, {"query": "  "}, {"query": 5}])
def test_socket_rejects_bad_payload(server, payload):
    assert _socket_events(server, payload) == [("chat_error", {"error": "Query is required"})]


def test_socket_hides_internal_errors(server, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("redis password=hunter2")

    monkeypatch.setattr(server.sessions, "get_history_for_openai", broken)

    assert _socket_events(server, {"query": "駅そば"}) == [("chat_error", {"error": "Internal server error"})]


# --- module-level app -------------------------------------------------------

def test_module_exposes_app_and_socketio_for_entry_points(chat_server):
    # run_chat_server.py does `from api.chat_server import app, socketio`
    assert chat_server.app.extensions["chat_server"] is not None
    assert chat_server.socketio.server is not None
