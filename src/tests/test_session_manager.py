"""
Unit tests for SessionManager
"""

import pytest
import time
import os
from services.session.session_manager import SessionManager, SessionMessage, ConversationSession


@pytest.fixture
def session_manager():
    """Create a SessionManager instance for testing"""
    # Force in-memory mode for testing
    os.environ["REDIS_URL"] = "redis://invalid:9999/0"  # Invalid Redis to force memory mode
    manager = SessionManager()
    manager.storage_type = "memory"  # Ensure we use memory mode
    manager.memory_store = {}  # Clear any existing data
    yield manager
    # Cleanup
    manager.memory_store = {}


def test_create_session(session_manager):
    """Test creating a new session"""
    session = session_manager.add_message("test_user", "user", "Hello", tokens=5)

    assert session.user_id == "test_user"
    assert len(session.messages) == 1
    assert session.messages[0].content == "Hello"
    assert session.messages[0].role == "user"
    assert session.total_tokens == 5


def test_get_session(session_manager):
    """Test retrieving a session"""
    # Create a session
    session_manager.add_message("test_user", "user", "Hello", tokens=5)

    # Retrieve it
    session = session_manager.get_session("test_user")
    assert session is not None
    assert session.user_id == "test_user"
    assert len(session.messages) == 1


def test_get_nonexistent_session(session_manager):
    """Test retrieving a session that doesn't exist"""
    session = session_manager.get_session("nonexistent_user")
    assert session is None


def test_add_multiple_messages(session_manager):
    """Test adding multiple messages to a session"""
    session_manager.add_message("test_user", "user", "Hello", tokens=5)
    session_manager.add_message("test_user", "assistant", "Hi there!", tokens=5)
    session_manager.add_message("test_user", "user", "How are you?", tokens=5)

    session = session_manager.get_session("test_user")
    assert len(session.messages) == 3
    assert session.total_tokens == 15
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"
    assert session.messages[2].role == "user"


def test_clear_session(session_manager):
    """Test clearing a session"""
    session_manager.add_message("test_user", "user", "Hello", tokens=5)
    session_manager.clear_session("test_user")

    session = session_manager.get_session("test_user")
    assert session is None


def test_trim_by_turns(session_manager):
    """Test trimming session by max turns"""
    session_manager.max_turns = 4

    # Add 6 messages (should trim to last 4)
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        session_manager.add_message("test_user", role, f"Message {i}", tokens=10)

    session = session_manager.get_session("test_user")
    assert len(session.messages) == 4  # Should trim to last 4
    assert session.messages[0].content == "Message 2"  # First should be message 2
    assert session.messages[-1].content == "Message 5"  # Last should be message 5


def test_trim_by_tokens(session_manager):
    """Test trimming session by max tokens"""
    session_manager.max_tokens = 50
    session_manager.max_turns = 100  # Set high to test token limit only

    # Add messages that exceed token limit
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        session_manager.add_message("test_user", role, f"Message {i}", tokens=20)

    session = session_manager.get_session("test_user")
    assert session.total_tokens <= 50  # Should be under limit
    assert len(session.messages) >= 2  # Should keep at least 2 messages


def test_session_expiry_memory(session_manager):
    """Test session expiry in memory mode"""
    session_manager.expiry_seconds = 1  # 1 second expiry

    session_manager.add_message("test_user", "user", "Hello", tokens=5)

    # Should exist immediately
    session = session_manager.get_session("test_user")
    assert session is not None

    # Wait for expiry
    time.sleep(2)

    # Should be expired
    session = session_manager.get_session("test_user")
    assert session is None


def test_get_history_for_openai(session_manager):
    """Test formatting history for OpenAI API"""
    session_manager.add_message("test_user", "user", "Hello", tokens=5)
    session_manager.add_message("test_user", "assistant", "Hi there!", tokens=5)
    session_manager.add_message("test_user", "user", "How are you?", tokens=5)

    history = session_manager.get_history_for_openai("test_user")

    assert len(history) == 3
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}
    assert history[2] == {"role": "user", "content": "How are you?"}


def test_get_history_empty(session_manager):
    """Test getting history for nonexistent session"""
    history = session_manager.get_history_for_openai("nonexistent_user")
    assert history == []


def test_cleanup_expired_sessions(session_manager):
    """Test cleanup of expired sessions"""
    session_manager.expiry_seconds = 1

    # Add multiple sessions
    session_manager.add_message("user1", "user", "Hello", tokens=5)
    session_manager.add_message("user2", "user", "Hello", tokens=5)

    # Wait for expiry
    time.sleep(2)

    # Run cleanup
    session_manager.cleanup_expired_sessions()

    # Both should be expired
    assert session_manager.get_session("user1") is None
    assert session_manager.get_session("user2") is None


def test_get_stats(session_manager):
    """Test getting session statistics"""
    session_manager.add_message("user1", "user", "Hello", tokens=5)
    session_manager.add_message("user2", "user", "Hello", tokens=5)

    stats = session_manager.get_stats()

    assert stats["storage_type"] == "memory"
    assert stats["active_sessions"] == 2
    assert stats["expiry_seconds"] == session_manager.expiry_seconds
    assert stats["max_turns"] == session_manager.max_turns
    assert stats["max_tokens"] == session_manager.max_tokens


def test_multi_user_isolation(session_manager):
    """Test that sessions are isolated between users"""
    session_manager.add_message("user1", "user", "User 1 message", tokens=5)
    session_manager.add_message("user2", "user", "User 2 message", tokens=5)

    session1 = session_manager.get_session("user1")
    session2 = session_manager.get_session("user2")

    assert session1.messages[0].content == "User 1 message"
    assert session2.messages[0].content == "User 2 message"
    assert len(session1.messages) == 1
    assert len(session2.messages) == 1


def test_session_ttl_refresh_on_access(session_manager):
    """Test that session TTL is refreshed on access"""
    session_manager.expiry_seconds = 2

    session_manager.add_message("test_user", "user", "Hello", tokens=5)

    # Wait 1 second
    time.sleep(1)

    # Access session (should refresh TTL)
    session = session_manager.get_session("test_user")
    assert session is not None

    # Wait another 1 second (total 2 seconds from creation, but 1 from access)
    time.sleep(1)

    # Should still exist because TTL was refreshed
    session = session_manager.get_session("test_user")
    assert session is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
