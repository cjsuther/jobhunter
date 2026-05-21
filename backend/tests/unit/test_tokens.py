"""JWT token unit tests."""

from uuid import uuid4

import pytest

from app.auth.tokens import TokenError, create_token, decode_token


def test_access_token_roundtrip():
    uid = uuid4()
    tok = create_token(uid, "user", "access")
    payload = decode_token(tok, expected="access")
    assert payload["sub"] == str(uid)
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_refresh_token_type_mismatch_rejected():
    tok = create_token(uuid4(), "user", "refresh")
    with pytest.raises(TokenError):
        decode_token(tok, expected="access")
