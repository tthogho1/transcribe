"""
Signed REST session ids.

The server issues every REST session id and signs it, so a client can only
use (export, clear, or chat with the history of) a session it was given.
"""

import logging
import os
import secrets
import uuid
from typing import Optional, Tuple

from itsdangerous import BadSignature, URLSafeSerializer

logger = logging.getLogger(__name__)


class UserTokens:
    """Issues and verifies the `user_id` tokens returned by /api/chat."""

    def __init__(self, secret_key: str):
        self._signer = URLSafeSerializer(secret_key, salt="chat-user-id")

    @classmethod
    def from_env(cls) -> "UserTokens":
        """Signed with FLASK_SECRET_KEY, or a random key if it isn't set."""
        secret_key = os.getenv("FLASK_SECRET_KEY")
        if not secret_key:
            logger.warning(
                "FLASK_SECRET_KEY is not set; using a random key, so REST user_ids "
                "become invalid when the server restarts"
            )
            secret_key = secrets.token_hex(32)
        return cls(secret_key)

    def issue(self) -> Tuple[str, str]:
        """Start a new session: returns (token for the client, session id)."""
        session_id = str(uuid.uuid4())
        return self._signer.dumps(session_id), session_id

    def verify(self, token: object) -> Optional[str]:
        """The session id inside a token this server issued, else None."""
        if not isinstance(token, str) or not token:
            return None
        try:
            session_id = self._signer.loads(token)
        except BadSignature:
            return None
        return session_id if isinstance(session_id, str) else None
