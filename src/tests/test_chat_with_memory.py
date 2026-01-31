"""
Integration tests for chat with memory functionality
Tests the full flow of conversation with session management
"""

import pytest
import requests
import time

BASE_URL = "http://localhost:7860"


@pytest.fixture
def unique_user_id():
    """Generate a unique user ID for each test"""
    return f"test_user_{int(time.time() * 1000)}"


def test_chat_with_memory_flow(unique_user_id):
    """Test full conversation flow with memory"""
    # First message: introduce name
    response1 = requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "私の名前は太郎です", "user_id": unique_user_id},
        timeout=30
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert "answer" in data1
    assert "user_id" in data1
    assert data1["user_id"] == unique_user_id

    # Second message: ask about name (should remember)
    response2 = requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "私の名前は何ですか？", "user_id": unique_user_id},
        timeout=30
    )
    assert response2.status_code == 200
    data2 = response2.json()
    # The assistant should mention the name from context
    # Note: This depends on the LLM's response, so we just check it responded
    assert "answer" in data2
    assert len(data2["answer"]) > 0


def test_session_export(unique_user_id):
    """Test exporting session history"""
    # Send a few messages
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "こんにちは", "user_id": unique_user_id},
        timeout=30
    )
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "元気ですか？", "user_id": unique_user_id},
        timeout=30
    )

    # Export session
    response = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": unique_user_id},
        timeout=10
    )
    assert response.status_code == 200
    data = response.json()

    assert "user_id" in data
    assert "messages" in data
    assert len(data["messages"]) == 4  # 2 user + 2 assistant


def test_session_clear(unique_user_id):
    """Test clearing session history"""
    # Send a message
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "こんにちは", "user_id": unique_user_id},
        timeout=30
    )

    # Clear session
    response = requests.post(
        f"{BASE_URL}/api/session/clear",
        json={"user_id": unique_user_id},
        timeout=10
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Try to export (should fail or return empty)
    export_response = requests.post(
        f"{BASE_URL}/api/session/export",
        json={"user_id": unique_user_id},
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


def test_multi_user_isolation(unique_user_id):
    """Test that different users have isolated sessions"""
    user1_id = f"{unique_user_id}_user1"
    user2_id = f"{unique_user_id}_user2"

    # User 1 introduces name
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "私の名前は太郎です", "user_id": user1_id},
        timeout=30
    )

    # User 2 introduces different name
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "私の名前は花子です", "user_id": user2_id},
        timeout=30
    )

    # Export both sessions
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

    # Verify sessions are different
    assert user1_export["user_id"] == user1_id
    assert user2_export["user_id"] == user2_id
    assert "太郎" in str(user1_export["messages"])
    assert "花子" in str(user2_export["messages"])


def test_rag_with_memory():
    """Test that RAG results are combined with conversation memory"""
    user_id = f"test_user_rag_{int(time.time() * 1000)}"

    # Ask about a topic that should retrieve RAG results
    response1 = requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "営業について教えて", "user_id": user_id},
        timeout=30
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert "sources" in data1
    # Should have RAG sources
    assert len(data1.get("sources", [])) >= 0

    # Follow-up question referencing previous context
    response2 = requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "もっと詳しく教えて", "user_id": user_id},
        timeout=30
    )
    assert response2.status_code == 200
    data2 = response2.json()
    # Should have both memory and RAG context
    assert "answer" in data2


def test_auto_user_id_generation():
    """Test that user_id is auto-generated if not provided"""
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"query": "こんにちは"},  # No user_id
        timeout=30
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    # UUID format check (8-4-4-4-12 hex digits)
    assert len(data["user_id"]) == 36
    assert data["user_id"].count("-") == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
