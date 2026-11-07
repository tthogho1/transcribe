"""
Integration tests for chat with memory functionality
Tests the full flow of conversation with session management

Needs a running server at BASE_URL. The server issues signed user_ids: the
first /api/chat call (without user_id) returns one, and later calls send it
back to continue that session.
"""

import pytest
import requests

BASE_URL = "http://localhost:7860"


def chat(query, user_id=None, timeout=30):
    """POST /api/chat; returns the response object."""
    payload = {"query": query}
    if user_id is not None:
        payload["user_id"] = user_id
    return requests.post(f"{BASE_URL}/api/chat", json=payload, timeout=timeout)


def start_session(query):
    """Send the first message of a new session; returns (json, issued user_id)."""
    response = chat(query)
    assert response.status_code == 200
    data = response.json()
    assert data.get("user_id")
    return data, data["user_id"]


def test_chat_with_memory_flow():
    """Test full conversation flow with memory"""
    # First message: introduce name
    data1, user_id = start_session("私の名前は太郎です")
    assert "answer" in data1

    # Second message: ask about name (should remember)
    response2 = chat("私の名前は何ですか？", user_id)
    assert response2.status_code == 200
    data2 = response2.json()
    # The same session continues
    assert data2["user_id"] == user_id
    # Note: the answer depends on the LLM, so we just check it responded
    assert len(data2["answer"]) > 0


def test_session_export():
    """Test exporting session history"""
    _, user_id = start_session("こんにちは")
    chat("元気ですか？", user_id)

    response = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": user_id},
        timeout=10
    )
    assert response.status_code == 200
    data = response.json()

    assert data["user_id"] == user_id
    assert len(data["messages"]) == 4  # 2 user + 2 assistant


def test_session_export_rejects_unissued_user_id():
    """A user_id the server didn't issue can't be used to read a session"""
    response = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": "user123"},
        timeout=10
    )
    assert response.status_code == 403


def test_session_clear():
    """Test clearing session history"""
    _, user_id = start_session("こんにちは")

    response = requests.post(
        f"{BASE_URL}/api/session/clear",
        json={"user_id": user_id},
        timeout=10
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # The session is gone
    export_response = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": user_id},
        timeout=10
    )
    assert export_response.status_code == 404  # No session found


def test_session_stats():
    """Test getting session statistics"""
    response = requests.get(f"{BASE_URL}/api/session/stats", timeout=10)
    assert response.status_code == 200
    data = response.json()

    assert "storage_type" in data
    assert data["storage_type"] in ["redis", "memory"]
    assert "active_sessions" in data
    assert isinstance(data["active_sessions"], int)


def test_health_check_with_session_info():
    """Test health check endpoint includes session information"""
    response = requests.get(f"{BASE_URL}/health", timeout=10)
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"
    assert "services" in data
    assert "session_storage" in data["services"]
    assert "active_sessions" in data["services"]


def test_multi_user_isolation():
    """Test that different users have isolated sessions"""
    _, user1_id = start_session("私の名前は太郎です")
    _, user2_id = start_session("私の名前は花子です")
    assert user1_id != user2_id

    user1_export = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": user1_id},
        timeout=10
    ).json()

    user2_export = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": user2_id},
        timeout=10
    ).json()

    assert user1_export["user_id"] == user1_id
    assert user2_export["user_id"] == user2_id
    assert "太郎" in str(user1_export["messages"])
    assert "花子" in str(user2_export["messages"])
    assert "花子" not in str(user1_export["messages"])


def test_rag_with_memory():
    """Test that RAG results are combined with conversation memory"""
    # Ask about a topic that should retrieve RAG results
    data1, user_id = start_session("営業について教えて")
    assert "sources" in data1

    # Follow-up question referencing previous context
    response2 = chat("もっと詳しく教えて", user_id)
    assert response2.status_code == 200
    assert "answer" in response2.json()


def test_auto_user_id_generation():
    """A user_id is issued when none is provided"""
    data, user_id = start_session("こんにちは")
    assert isinstance(user_id, str) and len(user_id) > 36  # signed, not a bare UUID


def test_unissued_user_id_gets_a_new_session():
    """A made-up user_id is replaced with a newly issued one"""
    response = chat("こんにちは", "user123")
    assert response.status_code == 200
    assert response.json()["user_id"] != "user123"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
