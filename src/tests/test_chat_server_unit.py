"""
Offline unit tests for api/chat_server.py.

chat_server builds a ChatService (Zilliz + embedding model) and a SessionManager
(Redis) at import time, so this module installs fakes for those before
importing it. No network or API keys are needed.
"""

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.conversation_chunk import SearchResult


@pytest.fixture(scope="module")
def chat_server():
    saved = {
        name: sys.modules.get(name)
        for name in ("core.conversation_vectorizer", "api.chat_server")
    }

    fake_vectorizer_mod = types.ModuleType("core.conversation_vectorizer")
    fake_vectorizer_mod.ConversationVectorizer = MagicMock(name="ConversationVectorizer")
    sys.modules["core.conversation_vectorizer"] = fake_vectorizer_mod
    sys.modules.pop("api.chat_server", None)

    mp = pytest.MonkeyPatch()
    mp.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # don't read the real .env
    mp.setenv("OPENAI_API_KEY", "test-key")  # OpenAI() needs a key; no call is made
    mp.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> memory storage
    try:
        module = importlib.import_module("api.chat_server")
    finally:
        mp.undo()

    yield module

    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


@pytest.fixture(autouse=True)
def no_network_translation(chat_server, monkeypatch):
    """Fail loudly instead of calling Google Translate."""
    def refuse(*a, **k):
        raise AssertionError("test tried to call Google Translate")

    monkeypatch.setattr(chat_server.chat_service.translator, "translate", refuse)
    monkeypatch.setattr(chat_server, "GoogleTranslator", MagicMock(side_effect=refuse))


def _openai_response(content, total_tokens=5000):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=total_tokens),
    )


def _result():
    return SearchResult(
        text="駅そばの話", speaker="A", timestamp="00:01", file_name="abc123.json",
        score=0.9, similarity=0.9, search_type="hybrid", title="Video",
    )


# --- language detection -----------------------------------------------------

@pytest.mark.parametrize("query", ["東京駅", "誉", "人工知能", "駅そば", "好きな食べ物は何", "ｶﾚｰ"])
def test_japanese_script_is_japanese(chat_server, query):
    assert chat_server.is_japanese_query(query) is True


@pytest.mark.parametrize("query", ["2024", "？", "!!!", ""])
def test_unclassifiable_query_defaults_to_japanese(chat_server, query):
    assert chat_server.is_japanese_query(query) is True


def test_english_query_is_not_japanese(chat_server):
    assert chat_server.is_japanese_query("What did you eat at the station?") is False


def test_detect_language_never_raises(chat_server):
    assert chat_server.detect_language("2024") == "unknown"


def test_kanji_only_query_is_answered_in_japanese(chat_server, monkeypatch):
    service = chat_server.chat_service
    monkeypatch.setattr(service, "search", lambda q, limit=5: [_result()])
    generate = MagicMock(return_value=chat_server.GeneratedAnswer("答え", 10))
    monkeypatch.setattr(service.generator, "generate", generate)
    translate = MagicMock()
    monkeypatch.setattr(service.translator, "translate", translate)

    service.process_chat_query("東京駅")

    answer_in_english = generate.call_args.args[3]
    assert answer_in_english is False
    translate.assert_not_called()


def test_digit_only_query_does_not_error(chat_server, monkeypatch):
    service = chat_server.chat_service
    monkeypatch.setattr(service, "search", lambda q, limit=5: [])
    monkeypatch.setattr(
        service.generator, "generate",
        MagicMock(return_value=chat_server.GeneratedAnswer("答え", 10)),
    )

    response = service.process_chat_query("2024")

    assert response.answer == "答え"


# --- empty / None answers ---------------------------------------------------

@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_openai_answer_becomes_error_message(chat_server, monkeypatch, content):
    service = chat_server.chat_service
    monkeypatch.setattr(service, "search", lambda q, limit=5: [_result()])
    monkeypatch.setattr(
        service.generator.client.chat.completions, "create",
        MagicMock(return_value=_openai_response(content)),
    )

    with pytest.raises(ValueError):
        service.generator.generate("質問", [_result()], [], False)

    response = service.process_chat_query("質問")
    assert response.error is True
    assert isinstance(response.answer, str) and "エラー" in response.answer


# --- session token accounting -----------------------------------------------

@pytest.fixture
def client_and_sessions(chat_server, monkeypatch):
    sessions = chat_server.session_manager
    monkeypatch.setattr(sessions, "storage_type", "memory")
    monkeypatch.setattr(sessions, "memory_store", {})
    return chat_server.app.test_client(), sessions


def test_session_keeps_history_when_calls_use_many_tokens(chat_server, monkeypatch, client_and_sessions):
    client, sessions = client_and_sessions
    service = chat_server.chat_service
    monkeypatch.setattr(service, "analyze_query", lambda q, h=None: chat_server.QueryAnalysis(True, q))
    monkeypatch.setattr(service, "search", lambda q, limit=5: [_result()])
    # Each call reports far more than MAX_CONVERSATION_TOKENS (default 4000).
    monkeypatch.setattr(
        service.generator, "generate",
        lambda *a, **kw: chat_server.GeneratedAnswer("答えです", 9000),
    )

    token = None
    for q in ["一つ目の質問", "二つ目の質問", "三つ目の質問"]:
        body = {"query": q} if token is None else {"query": q, "user_id": token}
        res = client.post("/api/chat", json=body)
        assert res.status_code == 200
        token = res.get_json()["user_id"]

    history = sessions.get_history_for_openai(chat_server.verify_user_token(token))
    assert [m["content"] for m in history if m["role"] == "user"] == [
        "一つ目の質問", "二つ目の質問", "三つ目の質問",
    ]
    assert len(history) == 6


# --- signed user_ids (#6) ---------------------------------------------------

@pytest.fixture
def fake_answers(chat_server, monkeypatch):
    service = chat_server.chat_service
    monkeypatch.setattr(service, "analyze_query", lambda q, h=None: chat_server.QueryAnalysis(True, q))
    monkeypatch.setattr(service, "search", lambda q, limit=5: [_result()])
    monkeypatch.setattr(
        service.generator, "generate",
        lambda *a, **kw: chat_server.GeneratedAnswer("答えです", 10),
    )


def test_token_round_trip(chat_server):
    token, session_id = chat_server.issue_user_token()
    assert chat_server.verify_user_token(token) == session_id


@pytest.mark.parametrize("bad", [None, "", "user123", 123, ["x"]])
def test_verify_rejects_unissued_tokens(chat_server, bad):
    assert chat_server.verify_user_token(bad) is None


def test_verify_rejects_tampered_token(chat_server):
    token, _ = chat_server.issue_user_token()
    other, _ = chat_server.issue_user_token()
    forged = other.split(".")[0] + "." + token.split(".")[-1]  # swap the payload
    assert chat_server.verify_user_token(forged) is None


def test_made_up_user_id_cannot_join_existing_session(chat_server, fake_answers, client_and_sessions):
    client, sessions = client_and_sessions
    # The victim's session is stored under its raw id.
    sessions.add_message("victim", "user", "秘密の話", tokens=1)

    res = client.post("/api/chat", json={"query": "さっきの話は？", "user_id": "victim"})

    assert res.status_code == 200
    new_token = res.get_json()["user_id"]
    assert new_token != "victim"
    assert chat_server.verify_user_token(new_token) != "victim"
    # The victim's history is untouched (nothing was appended to it).
    assert len(sessions.get_history_for_openai("victim")) == 1


@pytest.mark.parametrize("endpoint", ["/api/session/export", "/api/session/clear"])
def test_session_endpoints_reject_unissued_user_id(chat_server, client_and_sessions, endpoint):
    client, sessions = client_and_sessions
    sessions.add_message("victim", "user", "秘密の話", tokens=1)

    res = client.post(endpoint, json={"user_id": "victim"})

    assert res.status_code == 403
    assert "秘密の話" not in res.get_data(as_text=True)
    assert len(sessions.get_history_for_openai("victim")) == 1


def test_export_and_clear_work_with_issued_token(chat_server, fake_answers, client_and_sessions):
    client, _ = client_and_sessions
    token = client.post("/api/chat", json={"query": "こんにちは"}).get_json()["user_id"]

    export = client.post("/api/session/export", json={"user_id": token})
    assert export.status_code == 200
    assert export.get_json()["user_id"] == token
    assert len(export.get_json()["messages"]) == 2

    assert client.post("/api/session/clear", json={"user_id": token}).status_code == 200
    assert client.post("/api/session/export", json={"user_id": token}).status_code == 404


# --- error replies are not saved (#9) ---------------------------------------

def test_error_reply_is_not_saved_to_history(chat_server, monkeypatch, client_and_sessions):
    client, sessions = client_and_sessions
    service = chat_server.chat_service
    monkeypatch.setattr(service, "analyze_query", lambda q, h=None: chat_server.QueryAnalysis(False, q))
    monkeypatch.setattr(service, "search", lambda q, limit=5: [])

    def boom(*a, **kw):
        raise RuntimeError("openai down")

    monkeypatch.setattr(service.generator, "generate", boom)

    res = client.post("/api/chat", json={"query": "こんにちは"})

    assert res.status_code == 200
    session_id = chat_server.verify_user_token(res.get_json()["user_id"])
    assert sessions.get_history_for_openai(session_id) == []


def test_search_outage_returns_error_not_a_made_up_answer(chat_server, monkeypatch, client_and_sessions):
    """If Zilliz is down, the user gets an error, not an answer built from no context."""
    client, sessions = client_and_sessions
    service = chat_server.chat_service
    monkeypatch.setattr(service, "analyze_query", lambda q, h=None: chat_server.QueryAnalysis(False, q))

    def outage(q, limit=5):
        raise ConnectionError("zilliz down")

    monkeypatch.setattr(service, "search", outage)
    generate = MagicMock()
    monkeypatch.setattr(service.generator, "generate", generate)

    res = client.post("/api/chat", json={"query": "駅そばの話は？"})

    assert res.status_code == 200
    body = res.get_json()
    assert "エラー" in body["answer"]
    assert body["sources"] == []
    generate.assert_not_called()  # no answer is generated without search results
    session_id = chat_server.verify_user_token(body["user_id"])
    assert sessions.get_history_for_openai(session_id) == []


def test_processing_failure_is_marked_as_error(chat_server, monkeypatch):
    service = chat_server.chat_service

    def boom(q, limit=5):
        raise RuntimeError("zilliz down")

    monkeypatch.setattr(service, "search", boom)

    assert service.process_chat_query("こんにちは").error is True


# --- /api/search limit validation (#10) -------------------------------------

@pytest.mark.parametrize("limit", ["5", 0, -1, 21, 100000, 2.5, True, None])
def test_search_rejects_bad_limit(chat_server, monkeypatch, limit):
    search = MagicMock(return_value=[])
    monkeypatch.setattr(chat_server.chat_service, "search", search)

    res = chat_server.app.test_client().post("/api/search", json={"query": "駅そば", "limit": limit})

    assert res.status_code == 400
    search.assert_not_called()


@pytest.mark.parametrize("body, expected", [({}, 5), ({"limit": 1}, 1), ({"limit": 20}, 20)])
def test_search_accepts_valid_limit(chat_server, monkeypatch, body, expected):
    search = MagicMock(return_value=[_result()])
    monkeypatch.setattr(chat_server.chat_service, "search", search)

    res = chat_server.app.test_client().post("/api/search", json={"query": "駅そば", **body})

    assert res.status_code == 200
    search.assert_called_once_with("駅そば", expected)


# --- request validation and error responses ---------------------------------

@pytest.mark.parametrize("path", ["/api/chat", "/api/search", "/api/session/clear", "/api/session/export"])
@pytest.mark.parametrize("body, content_type", [
    ("not json", "text/plain"),
    ("[1, 2]", "application/json"),
    ("null", "application/json"),
    ("{broken", "application/json"),
])
def test_non_object_body_is_400(chat_server, path, body, content_type):
    res = chat_server.app.test_client().post(path, data=body, content_type=content_type)

    assert res.status_code == 400
    assert res.get_json() == {"error": "Request body must be a JSON object"}


@pytest.mark.parametrize("query", [123, None, ["駅そば"], "   "])
def test_non_string_or_blank_query_is_400(chat_server, query):
    res = chat_server.app.test_client().post("/api/chat", json={"query": query})

    assert res.status_code == 400
    assert res.get_json() == {"error": "Query is required"}


def test_unexpected_error_hides_details(chat_server, monkeypatch):
    def outage(q, limit=5):
        raise ConnectionError("zilliz down at in03-secret-host:19530")

    monkeypatch.setattr(chat_server.chat_service, "search", outage)

    res = chat_server.app.test_client().post("/api/search", json={"query": "駅そば"})

    assert res.status_code == 500
    assert res.get_json() == {"error": "Internal server error"}
    assert "secret-host" not in res.get_data(as_text=True)


def test_unknown_route_is_still_404(chat_server):
    client = chat_server.app.test_client()
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/chat").status_code == 405  # POST only


def test_json_keeps_japanese_readable(chat_server, fake_answers, client_and_sessions):
    client, _ = client_and_sessions
    raw = client.post("/api/chat", json={"query": "こんにちは"}).get_data(as_text=True)
    assert "答えです" in raw  # not \\u7b54...


# --- Socket.IO --------------------------------------------------------------

def _socket_events(chat_server, *payloads):
    sc = chat_server.socketio.test_client(chat_server.app)
    for p in payloads:
        sc.emit("chat_message", p)
    events = sc.get_received()
    sc.disconnect()
    return [(e["name"], e["args"][0]) for e in events if e["name"] != "status"]


def test_socket_chat_answers_and_remembers(chat_server, fake_answers, client_and_sessions):
    _, sessions = client_and_sessions

    events = _socket_events(chat_server, {"query": " 駅そば "})

    ((name, payload),) = events
    assert name == "chat_response"
    assert payload["answer"] == "答えです"
    assert payload["sources"][0]["text"] == "駅そばの話"
    assert "user_id" not in payload  # the socket connection is the session
    (session_id,) = sessions.memory_store
    assert [m["content"] for m in sessions.get_history_for_openai(session_id)] == ["駅そば", "答えです"]


@pytest.mark.parametrize("payload", [None, "駅そば", {}, {"query": "  "}, {"query": 5}])
def test_socket_rejects_bad_payload(chat_server, client_and_sessions, payload):
    assert _socket_events(chat_server, payload) == [("chat_error", {"error": "Query is required"})]
