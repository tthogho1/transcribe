"""
Session management for chatbot conversations
Supports both Redis (production) and in-memory (development) storage
"""

import os
import json
import time
import logging
import threading
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class SessionMessage:
    """Single message in conversation history"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    tokens: int = 0


@dataclass
class ConversationSession:
    """Complete conversation session"""
    user_id: str
    messages: List[SessionMessage]
    created_at: str
    last_accessed: str
    total_tokens: int


class SessionManager:
    """Manages conversation sessions with Redis (primary) or in-memory (fallback)"""

    def __init__(self):
        self.expiry_seconds = int(os.getenv("SESSION_EXPIRY_SECONDS", "1800"))  # 30 min
        self.max_turns = int(os.getenv("MAX_CONVERSATION_TURNS", "20"))
        self.max_tokens = int(os.getenv("MAX_CONVERSATION_TOKENS", "4000"))

        # Try Redis first, fallback to in-memory
        self.storage_type = "redis"
        self.redis_client = None
        self.memory_store = {}  # Fallback storage
        self.memory_lock = threading.Lock()  # Thread safety for in-memory

        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize Redis or fallback to in-memory"""
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.redis_client = redis.from_url(redis_url, decode_responses=True)

            # Test connection
            self.redis_client.ping()
            logger.info("✅ SessionManager: Using Redis storage")
            self.storage_type = "redis"

        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable: {e}, using in-memory storage")
            self.storage_type = "memory"
            self.memory_store = {}

    def get_session(self, user_id: str) -> Optional[ConversationSession]:
        """Retrieve conversation session"""
        try:
            if self.storage_type == "redis":
                return self._get_session_redis(user_id)
            else:
                return self._get_session_memory(user_id)
        except Exception as e:
            logger.error(f"Error getting session for {user_id}: {e}")
            return None

    def save_session(self, session: ConversationSession):
        """Save conversation session"""
        try:
            if self.storage_type == "redis":
                self._save_session_redis(session)
            else:
                self._save_session_memory(session)
        except Exception as e:
            logger.error(f"Error saving session for {session.user_id}: {e}")

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        tokens: int = 0
    ) -> ConversationSession:
        """Add message to session and return updated session"""
        session = self.get_session(user_id)

        if session is None:
            # Create new session
            session = ConversationSession(
                user_id=user_id,
                messages=[],
                created_at=datetime.now().isoformat(),
                last_accessed=datetime.now().isoformat(),
                total_tokens=0
            )

        # Add new message
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            tokens=tokens
        )
        session.messages.append(message)
        session.total_tokens += tokens
        session.last_accessed = datetime.now().isoformat()

        # Trim if necessary
        session = self._trim_session(session)

        # Save
        self.save_session(session)

        return session

    def clear_session(self, user_id: str):
        """Clear session for user"""
        try:
            if self.storage_type == "redis":
                self.redis_client.delete(f"session:{user_id}")
            else:
                with self.memory_lock:
                    self.memory_store.pop(user_id, None)
            logger.info(f"Cleared session for {user_id}")
        except Exception as e:
            logger.error(f"Error clearing session for {user_id}: {e}")

    def get_history_for_openai(self, user_id: str) -> List[Dict]:
        """Get conversation history formatted for OpenAI API"""
        session = self.get_session(user_id)
        if not session:
            return []

        return [
            {"role": msg.role, "content": msg.content}
            for msg in session.messages
        ]

    # Redis implementation
    def _get_session_redis(self, user_id: str) -> Optional[ConversationSession]:
        key = f"session:{user_id}"
        data = self.redis_client.get(key)

        if not data:
            return None

        # Refresh TTL on access
        self.redis_client.expire(key, self.expiry_seconds)

        # Deserialize
        session_dict = json.loads(data)
        session_dict["messages"] = [
            SessionMessage(**msg) for msg in session_dict["messages"]
        ]
        return ConversationSession(**session_dict)

    def _save_session_redis(self, session: ConversationSession):
        key = f"session:{session.user_id}"

        # Serialize
        session_dict = asdict(session)
        data = json.dumps(session_dict, ensure_ascii=False)

        # Save with TTL
        self.redis_client.setex(key, self.expiry_seconds, data)

    # In-memory implementation
    def _get_session_memory(self, user_id: str) -> Optional[ConversationSession]:
        with self.memory_lock:
            if user_id not in self.memory_store:
                return None

            session, expiry_time = self.memory_store[user_id]

            # Check expiry
            if time.time() > expiry_time:
                del self.memory_store[user_id]
                return None

            # Update expiry on access
            self.memory_store[user_id] = (session, time.time() + self.expiry_seconds)

            return session

    def _save_session_memory(self, session: ConversationSession):
        with self.memory_lock:
            expiry_time = time.time() + self.expiry_seconds
            self.memory_store[session.user_id] = (session, expiry_time)

    def _trim_session(self, session: ConversationSession) -> ConversationSession:
        """Trim session by turns and tokens"""
        messages = session.messages

        # Trim by turns
        if len(messages) > self.max_turns:
            messages = messages[-self.max_turns:]

        # Trim by tokens
        total_tokens = sum(m.tokens for m in messages)
        while total_tokens > self.max_tokens and len(messages) > 2:
            removed = messages.pop(0)
            total_tokens -= removed.tokens

        session.messages = messages
        session.total_tokens = total_tokens

        return session

    def cleanup_expired_sessions(self):
        """Clean up expired sessions from memory storage"""
        if self.storage_type != "memory":
            return

        with self.memory_lock:
            now = time.time()
            expired = [
                uid for uid, (_, exp) in self.memory_store.items()
                if exp <= now
            ]

            for uid in expired:
                del self.memory_store[uid]

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")

    def get_stats(self) -> Dict:
        """Get session manager statistics"""
        try:
            if self.storage_type == "redis":
                keys = self.redis_client.keys("session:*")
                active_sessions = len(keys)
            else:
                # Clean expired sessions first
                self.cleanup_expired_sessions()
                with self.memory_lock:
                    active_sessions = len(self.memory_store)

            return {
                "storage_type": self.storage_type,
                "active_sessions": active_sessions,
                "expiry_seconds": self.expiry_seconds,
                "max_turns": self.max_turns,
                "max_tokens": self.max_tokens
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}
