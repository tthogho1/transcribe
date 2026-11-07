"""Tests for api/auth.py."""

import pytest

from api.auth import UserTokens


@pytest.fixture
def tokens():
    return UserTokens("test-secret")


def test_token_round_trip(tokens):
    token, session_id = tokens.issue()
    assert tokens.verify(token) == session_id


def test_each_token_is_a_new_session(tokens):
    assert tokens.issue()[1] != tokens.issue()[1]


@pytest.mark.parametrize("bad", [None, "", "user123", 123, ["x"]])
def test_verify_rejects_unissued_tokens(tokens, bad):
    assert tokens.verify(bad) is None


def test_verify_rejects_tampered_token(tokens):
    token, _ = tokens.issue()
    other, _ = tokens.issue()
    forged = other.split(".")[0] + "." + token.split(".")[-1]  # swap the payload
    assert tokens.verify(forged) is None


def test_token_from_another_key_is_rejected(tokens):
    token, _ = UserTokens("other-secret").issue()
    assert tokens.verify(token) is None


def test_from_env_without_secret_still_works(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    tokens = UserTokens.from_env()
    token, session_id = tokens.issue()
    assert tokens.verify(token) == session_id
